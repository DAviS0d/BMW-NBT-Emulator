import { AudioCodec, type AudioConfigMessage, type AudioPacketMessage } from './protocol';

interface StreamState {
  codec: number;
  sampleRate: number;
  channels: number;
  name: string;
  decoder: AudioDecoder | null;
  nextPlayTime: number;
  gain: GainNode;
}

const MIN_LATENCY_SECONDS = 0.12;
const MAX_LATENCY_SECONDS = 0.35;

/** Decodes and plays CarPlay audio streams (AAC-LC, Opus, LPCM) via Web Audio. */
export class AudioEngine {
  private readonly context: AudioContext;
  private readonly gain: GainNode;
  private readonly streams = new Map<number, StreamState>();
  private readonly streamGains = new Map<string, number>();
  private unlocked = false;

  constructor(private readonly onError: (message: string) => void) {
    this.context = new AudioContext({ latencyHint: 'interactive' });
    this.gain = this.context.createGain();
    this.gain.connect(this.context.destination);
  }

  get isUnlocked(): boolean {
    return this.unlocked;
  }

  get outputVolume(): number { return this.gain.gain.value; }
  get activeStreamCount(): number { return this.streams.size; }

  /** Must run inside a user gesture so the browser allows audio playback. */
  async unlock(): Promise<void> {
    await this.context.resume();
    this.unlocked = true;
  }

  setVolume(volume: number): void {
    this.gain.gain.value = Math.min(1, Math.max(0, volume));
  }

  setStreamGain(name: string, value: number): void {
    const gain = Math.min(1, Math.max(0, value));
    this.streamGains.set(name, gain);
    for (const state of this.streams.values()) {
      if (state.name === name) state.gain.gain.value = gain;
    }
  }

  activeStreamNames(): string[] {
    return Array.from(new Set(Array.from(this.streams.values(), (state) => state.name))).sort();
  }

  handleConfig(message: AudioConfigMessage): void {
    this.closeStream(message.streamType);
    const streamGain = this.context.createGain();
    streamGain.gain.value = this.streamGains.get(message.name) ?? 1;
    streamGain.connect(this.gain);
    const state: StreamState = {
      codec: message.codec,
      sampleRate: message.sampleRate,
      channels: message.channels,
      name: message.name,
      decoder: null,
      nextPlayTime: 0,
      gain: streamGain,
    };
    if (message.codec === AudioCodec.AacLc || message.codec === AudioCodec.Opus) {
      if (typeof AudioDecoder === 'undefined') {
        this.onError(
          'WebCodecs audio decoding needs a secure context. Open the https:// URL printed by the server.',
        );
        this.streams.set(message.streamType, state);
        return;
      }
      let decoder: AudioDecoder;
      try {
        decoder = new AudioDecoder({
          output: (data) => {
            try {
              this.playAudioData(state, data);
            } finally {
              data.close();
            }
          },
          error: (error) => this.onError(`Audio decoder error: ${error.message}`),
        });
        const config: AudioDecoderConfig =
          message.codec === AudioCodec.AacLc
            ? {
                codec: 'mp4a.40.2',
                sampleRate: message.sampleRate,
                numberOfChannels: message.channels,
                description: message.description.length > 0 ? message.description : undefined,
              }
            : {
                codec: 'opus',
                sampleRate: message.sampleRate,
                numberOfChannels: message.channels,
              };
        decoder.configure(config);
        state.decoder = decoder;
      } catch (error) {
        this.onError(`Audio decoder rejected ${message.codec === AudioCodec.AacLc ? 'AAC' : 'Opus'}: ${describeError(error)}`);
      }
    }
    this.streams.set(message.streamType, state);
  }

  handlePacket(message: AudioPacketMessage): void {
    const state = this.streams.get(message.streamType);
    if (!state) return;
    if (state.decoder) {
      try {
        state.decoder.decode(
          new EncodedAudioChunk({
            type: 'key',
            timestamp: message.timestampUs,
            data: message.data,
          }),
        );
      } catch (error) {
        this.onError(`Audio decode failed: ${describeError(error)}`);
      }
      return;
    }
    if (state.codec === AudioCodec.Lpcm) {
      this.playPcm(state, message.data);
    }
  }

  stopStream(streamType: number): void {
    this.closeStream(streamType);
  }

  stopAll(): void {
    for (const streamType of this.streams.keys()) this.closeStream(streamType);
  }

  private closeStream(streamType: number): void {
    const state = this.streams.get(streamType);
    if (!state) return;
    this.streams.delete(streamType);
    runCatchingDisconnect(state.gain);
    if (state.decoder) {
      try {
        state.decoder.close();
      } catch {
        // Already closed.
      }
    }
  }

  private playAudioData(state: StreamState, data: AudioData): void {
    if (!this.unlocked) return;
    const numberOfChannels = Math.max(1, data.numberOfChannels);
    const buffer = this.context.createBuffer(numberOfChannels, data.numberOfFrames, data.sampleRate);
    for (let channel = 0; channel < numberOfChannels; channel += 1) {
      const plane = new Float32Array(data.numberOfFrames);
      data.copyTo(plane, { planeIndex: channel, format: 'f32-planar' });
      buffer.copyToChannel(plane, channel);
    }
    this.schedule(state, buffer);
  }

  private playPcm(state: StreamState, payload: Uint8Array): void {
    if (!this.unlocked || payload.length < 2) return;
    const sampleCount = Math.floor(payload.length / 2);
    const channels = Math.max(1, state.channels);
    const frames = Math.max(1, Math.floor(sampleCount / channels));
    const view = new DataView(payload.buffer, payload.byteOffset, payload.byteLength);
    const buffer = this.context.createBuffer(channels, frames, state.sampleRate);
    for (let channel = 0; channel < channels; channel += 1) {
      const plane = new Float32Array(frames);
      for (let frame = 0; frame < frames; frame += 1) {
        const offset = (frame * channels + channel) * 2;
        plane[frame] = view.getInt16(offset, true) / 32768;
      }
      buffer.copyToChannel(plane, channel);
    }
    this.schedule(state, buffer);
  }

  private schedule(state: StreamState, buffer: AudioBuffer): void {
    const now = this.context.currentTime;
    if (state.nextPlayTime < now + MIN_LATENCY_SECONDS || state.nextPlayTime > now + MAX_LATENCY_SECONDS) {
      state.nextPlayTime = now + MIN_LATENCY_SECONDS;
    }
    const source = this.context.createBufferSource();
    source.buffer = buffer;
    source.connect(state.gain);
    source.start(state.nextPlayTime);
    state.nextPlayTime += buffer.duration;
  }
}

function describeError(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error);
}

function runCatchingDisconnect(node: AudioNode): void {
  try {
    node.disconnect();
  } catch {
    // Already disconnected.
  }
}
