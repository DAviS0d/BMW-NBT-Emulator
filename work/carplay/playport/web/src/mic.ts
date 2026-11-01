/** Browser microphone uplink: captures PCM and sends it to the CarPlay speech/telephony stream. */

export interface MicRequest {
  sampleRate: number;
  channels: number;
  codec: string;
  samplesPerPacket: number;
  bitrate: number | null;
}

const WORKLET_SOURCE = `
class CarplayMic extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const configured = options && options.processorOptions && options.processorOptions.packetSamples;
    this.packetSamples = configured && configured > 0 ? configured : 320;
    this.buffer = new Float32Array(this.packetSamples);
    this.offset = 0;
  }
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (!channel) return true;
    for (let index = 0; index < channel.length; index += 1) {
      this.buffer[this.offset] = channel[index];
      this.offset += 1;
      if (this.offset === this.packetSamples) {
        const packet = new Float32Array(this.buffer);
        this.port.postMessage(packet, [packet.buffer]);
        this.offset = 0;
      }
    }
    return true;
  }
}
registerProcessor('carplay-mic', CarplayMic);
`;

export class MicrophoneUplink {
  private stream: MediaStream | null = null;
  private context: AudioContext | null = null;
  private node: AudioWorkletNode | null = null;
  private encoder: AudioEncoder | null = null;
  private encoderTimestampUs = 0;
  private active = false;
  private workletUrl: string | null = null;

  constructor(
    private readonly send: (payload: Uint8Array, opus: boolean) => void,
    private readonly onStatus: (message: string) => void,
  ) {}

  get isActive(): boolean {
    return this.active;
  }

  async start(request: MicRequest): Promise<void> {
    await this.stop();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: Math.max(1, Math.min(2, request.channels)),
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      const context = new AudioContext({ sampleRate: request.sampleRate });
      await context.resume();
      const url = this.workletSourceUrl();
      await context.audioWorklet.addModule(url);
      const node = new AudioWorkletNode(context, 'carplay-mic', {
        numberOfInputs: 1,
        numberOfOutputs: 0,
        processorOptions: { packetSamples: Math.max(1, request.samplesPerPacket) },
      });
      const source = context.createMediaStreamSource(stream);
      source.connect(node);
      node.port.onmessage = (event: MessageEvent<Float32Array>) => {
        this.onSamples(event.data);
      };
      if (request.codec === 'opus' && typeof AudioEncoder !== 'undefined') {
        const encoder = new AudioEncoder({
          output: (chunk) => {
            const payload = new Uint8Array(chunk.byteLength);
            chunk.copyTo(payload);
            this.send(payload, true);
          },
          error: (error) => this.onStatus(`Microphone encoder error: ${error.message}`),
        });
        encoder.configure({
          codec: 'opus',
          sampleRate: request.sampleRate,
          numberOfChannels: 1,
          bitrate: request.bitrate ?? 32_000,
        });
        this.encoder = encoder;
        this.encoderTimestampUs = 0;
      }
      this.stream = stream;
      this.context = context;
      this.node = node;
      this.active = true;
      this.onStatus(`Microphone live (${request.sampleRate} Hz, ${request.codec})`);
    } catch (error) {
      this.onStatus(`Microphone unavailable: ${describeError(error)}`);
      await this.stop();
    }
  }

  async stop(): Promise<void> {
    this.active = false;
    const encoder = this.encoder;
    this.encoder = null;
    if (encoder) {
      try {
        encoder.close();
      } catch {
        // Already closed.
      }
    }
    const node = this.node;
    this.node = null;
    if (node) {
      node.port.onmessage = null;
      try {
        node.disconnect();
      } catch {
        // Already disconnected.
      }
    }
    const context = this.context;
    this.context = null;
    if (context) {
      try {
        await context.close();
      } catch {
        // Already closed.
      }
    }
    const stream = this.stream;
    this.stream = null;
    stream?.getTracks().forEach((track) => track.stop());
  }

  private onSamples(samples: Float32Array): void {
    if (this.encoder) {
      const context = this.context;
      if (!context) return;
      const data = new AudioData({
        format: 'f32-planar',
        sampleRate: context.sampleRate,
        numberOfFrames: samples.length,
        numberOfChannels: 1,
        timestamp: this.encoderTimestampUs,
        data: new Float32Array(samples),
      });
      this.encoderTimestampUs += Math.round((samples.length / context.sampleRate) * 1_000_000);
      try {
        this.encoder.encode(data);
      } finally {
        data.close();
      }
      return;
    }
    const pcm = new Uint8Array(samples.length * 2);
    const view = new DataView(pcm.buffer);
    for (let index = 0; index < samples.length; index += 1) {
      const clamped = Math.max(-1, Math.min(1, samples[index]));
      view.setInt16(index * 2, Math.round(clamped * 32767), true);
    }
    this.send(pcm, false);
  }

  private workletSourceUrl(): string {
    if (this.workletUrl) return this.workletUrl;
    const blob = new Blob([WORKLET_SOURCE], { type: 'application/javascript' });
    this.workletUrl = URL.createObjectURL(blob);
    return this.workletUrl;
  }
}

function describeError(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error);
}
