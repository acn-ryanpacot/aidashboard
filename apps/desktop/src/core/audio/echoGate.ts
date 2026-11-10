/**
 * Echo-aware barge-in detection ("double-talk detection").
 *
 * While Jarvis speaks through loudspeakers, the microphone hears Jarvis too.
 * A plain voice detector would interrupt Jarvis with its own voice. The
 * {@link EchoGate} instead learns how much of the *output* leaks into the
 * *input* (the echo path) and only reports user speech when the microphone
 * is clearly louder than the expected echo, for long enough.
 *
 * It runs on the client because only the client knows both signals: the mic
 * frame and what the speakers are playing at that instant. See
 * docs/adr/0013-echo-aware-barge-in.md.
 *
 * @module
 */

/** Tuning for {@link EchoGate}. */
export interface EchoGateOptions {
  /** Consecutive "speech" frames required to trigger (e.g. 5 × 80 ms = 400 ms). */
  readonly minSpeechFrames: number;
  /** How far above the expected echo the mic must be (×). */
  readonly echoMargin?: number;
  /** How far above the room's noise floor the mic must be (×). */
  readonly noiseMargin?: number;
  /** Absolute minimum mic RMS for speech (full scale = 1). */
  readonly minLevel?: number;
}

/** Output level above which the leak estimate is updated. */
const LOUD_OUTPUT = 0.02;
/** Smoothing for the adaptive estimates (per frame). */
const ADAPT = 0.06;
/** Echo arrives late; compare against the loudest of the last N output readings. */
const OUTPUT_HISTORY = 4;

/** RMS of 16-bit PCM samples, normalised to 0…1. */
export function pcm16Rms(samples: Int16Array): number {
  if (samples.length === 0) return 0;
  let sum = 0;
  for (const sample of samples) sum += (sample / 32768) ** 2;
  return Math.sqrt(sum / samples.length);
}

/** RMS of float samples in [-1, 1]. */
export function floatRms(samples: Float32Array): number {
  if (samples.length === 0) return 0;
  let sum = 0;
  for (const sample of samples) sum += sample * sample;
  return Math.sqrt(sum / samples.length);
}

/** Adaptive double-talk detector. One instance per microphone. */
export class EchoGate {
  readonly #minFrames: number;
  readonly #echoMargin: number;
  readonly #noiseMargin: number;
  readonly #minLevel: number;
  #leak = 0.5; // conservative start: assume half the output leaks back
  #noiseFloor = 0.004;
  #streak = 0;
  #outputs: number[] = [];

  constructor(options: EchoGateOptions) {
    this.#minFrames = Math.max(1, options.minSpeechFrames);
    this.#echoMargin = options.echoMargin ?? 2.2;
    this.#noiseMargin = options.noiseMargin ?? 3;
    this.#minLevel = options.minLevel ?? 0.012;
  }

  /** Current estimate of the speaker→mic leakage ratio (for diagnostics). */
  get leak(): number {
    return this.#leak;
  }

  /**
   * Feed one frame's levels.
   *
   * @param mic - Microphone RMS for the frame.
   * @param output - Playback RMS at the same moment (0 when silent).
   * @returns `true` once the user has spoken over the output long enough.
   */
  push(mic: number, output: number): boolean {
    this.#outputs.push(output);
    if (this.#outputs.length > OUTPUT_HISTORY) this.#outputs.shift();
    const recentOutput = Math.max(...this.#outputs);

    const threshold = Math.max(
      this.#minLevel,
      this.#noiseFloor * this.#noiseMargin,
      this.#leak * recentOutput * this.#echoMargin,
    );
    if (mic > threshold) {
      this.#streak += 1;
      if (this.#streak >= this.#minFrames) {
        this.#streak = 0;
        return true;
      }
      return false;
    }

    // Not speech: learn from it.
    this.#streak = 0;
    if (recentOutput > LOUD_OUTPUT) {
      const ratio = Math.min(2, Math.max(0.01, mic / recentOutput));
      this.#leak += ADAPT * (ratio - this.#leak);
    } else {
      this.#noiseFloor += ADAPT * (mic - this.#noiseFloor);
    }
    return false;
  }

  /** Forget the current speech streak (e.g. when playback stops). */
  reset(): void {
    this.#streak = 0;
    this.#outputs = [];
  }
}

/** Fixed-size buffer of the most recent microphone frames. */
export class FrameRing {
  readonly #capacity: number;
  #frames: ArrayBuffer[] = [];

  constructor(capacity: number) {
    this.#capacity = Math.max(1, capacity);
  }

  push(frame: ArrayBuffer): void {
    this.#frames.push(frame);
    if (this.#frames.length > this.#capacity) this.#frames.shift();
  }

  /** Remove and return everything, oldest first. */
  drain(): ArrayBuffer[] {
    const frames = this.#frames;
    this.#frames = [];
    return frames;
  }

  clear(): void {
    this.#frames = [];
  }
}
