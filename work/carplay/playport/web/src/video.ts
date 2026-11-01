import { annexBToAvcc, avcCodecString, VideoCodec, type VideoConfigMessage, type VideoFrameMessage } from './protocol';

interface DecoderState {
  decoder: VideoDecoder;
  usesDescription: boolean;
  timestampUs: number;
  frameIntervalUs: number;
  width: number;
  height: number;
}

interface HevcCandidate {
  codec: string;
  description?: Uint8Array;
  software: boolean;
}

const STALL_TIMEOUT_MS = 2500;

/** Decodes CarPlay's H.264/H.265 stream with WebCodecs and paints it to a canvas. */
export class VideoPlayer {
  private state: DecoderState | null = null;
  private lastConfig: VideoConfigMessage | null = null;
  private preferHardware = true;
  private generation = 0;
  private watchdog: number | null = null;
  private framesRendered = 0;
  private lastFrameSize = { width: 0, height: 0 };

  constructor(
    private readonly canvas: HTMLCanvasElement,
    private readonly onError: (message: string) => void,
    private readonly onFrame: () => void,
    private readonly onRequestKeyframe: () => void,
    private readonly onResolutionChange: (width: number, height: number) => void = () => {},
  ) {}

  get isConfigured(): boolean {
    return this.state !== null;
  }

  get decodeQueueSize(): number {
    return this.state?.decoder.decodeQueueSize ?? 0;
  }

  /** Timestamp of the most recent frame arrival; used for the latency readout. */
  lastArrivalAt = 0;

  configure(message: VideoConfigMessage): void {
    void this.configureAsync(message);
  }

  private async configureAsync(message: VideoConfigMessage): Promise<void> {
    const generation = ++this.generation;
    this.close();
    this.lastConfig = message;
    if (typeof VideoDecoder === 'undefined') {
      this.onError(
        'WebCodecs video decoding needs a secure context. Open the https:// URL printed by the server ' +
          '(accept the certificate warning once), or use http://localhost.',
      );
      return;
    }
    try {
      if (message.codec === VideoCodec.H264) {
        this.configureH264(message, generation);
        return;
      }
      await this.configureH265(message, generation);
    } catch (error) {
      if (generation === this.generation) {
        this.fail(`Video decoder rejected the stream: ${describeError(error)}`);
      }
    }
  }

  private configureH264(message: VideoConfigMessage, generation: number): void {
    const descriptionPresent = message.codecData.length > 4;
    const config: VideoDecoderConfig = {
      codec: avcCodecString(message.codecData),
      codedWidth: message.width,
      codedHeight: message.height,
      hardwareAcceleration: this.preferHardware ? 'prefer-hardware' : 'no-preference',
      ...(descriptionPresent ? { description: message.codecData } : {}),
    };
    const decoder = this.createDecoder();
    decoder.configure(config);
    if (generation !== this.generation) {
      decoder.close();
      return;
    }
    this.adopt(decoder, descriptionPresent, message);
  }

  private async configureH265(message: VideoConfigMessage, generation: number): Promise<void> {
    const candidates = hevcCodecCandidates(message.codecData);
    for (const candidate of candidates) {
      if (generation !== this.generation) return;
      const config: VideoDecoderConfig = {
        codec: candidate.codec,
        codedWidth: message.width,
        codedHeight: message.height,
        hardwareAcceleration: candidate.software ? 'no-preference' : 'prefer-hardware',
        ...(candidate.description ? { description: candidate.description } : {}),
      };
      const support = await VideoDecoder.isConfigSupported(config).catch(() => null);
      if (generation !== this.generation) return;
      if (!support?.supported) continue;
      const decoder = this.createDecoder();
      try {
        decoder.configure(config);
      } catch (error) {
        decoder.close();
        continue;
      }
      this.adopt(decoder, candidate.description !== undefined, message);
      return;
    }
    this.onError(
      'This phone sent H.265/HEVC, but this browser cannot decode it. ' +
        'Switch the video codec back to H.264 in the Display panel.',
    );
    this.onRequestKeyframe();
  }

  private adopt(decoder: VideoDecoder, usesDescription: boolean, message: VideoConfigMessage): void {
    this.state = {
      decoder,
      usesDescription,
      timestampUs: 0,
      frameIntervalUs: Math.round(1_000_000 / 60),
      width: message.width,
      height: message.height,
    };
    this.resizeCanvas(message.width, message.height);
    this.onResolutionChange(message.width, message.height);
    this.framesRendered = 0;
    this.armWatchdog();
    this.onError('');
  }

  pushFrame(message: VideoFrameMessage): void {
    const state = this.state;
    if (!state) return;
    this.lastArrivalAt = performance.now();
    const data = state.usesDescription ? annexBToAvcc(message.data) : message.data;
    if (data.length === 0) return;
    state.timestampUs += state.frameIntervalUs;
    try {
      state.decoder.decode(
        new EncodedVideoChunk({
          type: message.keyframe ? 'key' : 'delta',
          timestamp: state.timestampUs,
          data,
        }),
      );
    } catch (error) {
      this.fail(`Video decode failed: ${describeError(error)}`);
    }
  }

  close(): void {
    const state = this.state;
    this.state = null;
    this.clearWatchdog();
    if (state) {
      try {
        state.decoder.close();
      } catch {
        // Already closed.
      }
    }
  }

  /**
   * Tears the decoder down and recovers: silently retries in software when the hardware decoder
   * failed, and asks the phone for a fresh keyframe (which also re-sends the codec config).
   */
  private fail(message: string): void {
    this.close();
    if (this.preferHardware) {
      this.preferHardware = false;
      if (this.lastConfig) {
        this.configure(this.lastConfig);
        return;
      }
    }
    this.onError(message);
    this.onRequestKeyframe();
  }

  private createDecoder(): VideoDecoder {
    return new VideoDecoder({
      output: (frame) => {
        try {
          this.paint(frame);
        } finally {
          frame.close();
        }
      },
      error: (error) => this.fail(`Video decoder error: ${error.message}`),
    });
  }

  private armWatchdog(): void {
    this.clearWatchdog();
    this.watchdog = window.setTimeout(() => {
      this.watchdog = null;
      if (this.state && this.framesRendered === 0) {
        this.onRequestKeyframe();
        this.armWatchdog();
      }
    }, STALL_TIMEOUT_MS);
  }

  private clearWatchdog(): void {
    if (this.watchdog !== null) {
      window.clearTimeout(this.watchdog);
      this.watchdog = null;
    }
  }

  private paint(frame: VideoFrame): void {
    this.framesRendered += 1;
    this.clearWatchdog();
    const context = this.canvas.getContext('2d');
    if (!context) return;
    if (frame.displayWidth !== this.lastFrameSize.width || frame.displayHeight !== this.lastFrameSize.height) {
      this.lastFrameSize = { width: frame.displayWidth, height: frame.displayHeight };
      this.resizeCanvas(frame.displayWidth, frame.displayHeight);
      this.onResolutionChange(frame.displayWidth, frame.displayHeight);
    }
    context.drawImage(frame, 0, 0, this.canvas.width, this.canvas.height);
    this.onFrame();
  }

  private resizeCanvas(width: number, height: number): void {
    if (width > 0 && height > 0) {
      this.canvas.width = width;
      this.canvas.height = height;
    }
  }
}

/**
 * Builds HEVC codec strings from an hvcC record, most specific first.
 *
 * WebCodecs accepts `hvc1` with an hvcC description; the profile-compatibility flags in the codec
 * string are bit-reversed relative to the record (ISO/IEC 14496-15).
 */
function hevcCodecCandidates(hvcC: Uint8Array): HevcCandidate[] {
  const candidates: HevcCandidate[] = [];
  if (hvcC.length >= 13) {
    const view = new DataView(hvcC.buffer, hvcC.byteOffset, hvcC.byteLength);
    const profileSpace = ['', 'A', 'B', 'C'][(hvcC[1] >> 6) & 0x03] ?? '';
    const tier = (hvcC[1] & 0x20) !== 0 ? 'H' : 'L';
    const profileIdc = hvcC[1] & 0x1f;
    const compat = reverseBits32(view.getUint32(2)) >>> 0;
    const levelIdc = hvcC[12];
    const constraints: number[] = [];
    for (let index = 6; index <= 11; index += 1) constraints.push(hvcC[index]);
    while (constraints.length > 0 && constraints[constraints.length - 1] === 0) constraints.pop();
    const constraintHex = constraints
      .map((value) => value.toString(16).padStart(2, '0'))
      .join('')
      .toUpperCase();
    const base = `hvc1.${profileSpace}${profileIdc}.${compat.toString(16)}.${tier}${levelIdc}`;
    if (constraintHex) candidates.push({ codec: `${base}.${constraintHex}`, description: hvcC, software: false });
    candidates.push({ codec: base, description: hvcC, software: false });
    candidates.push({ codec: base, description: hvcC, software: true });
  }
  candidates.push({ codec: 'hvc1.1.6.L120.B0', description: hvcC, software: true });
  return candidates;
}

function reverseBits32(value: number): number {
  let result = 0;
  for (let index = 0; index < 32; index += 1) {
    result = ((result << 1) | (value & 1)) >>> 0;
    value >>>= 1;
  }
  return result >>> 0;
}

function describeError(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error);
}
