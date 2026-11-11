/**
 * UI sound design: short synthesised "earcons", so you know Jarvis heard you
 * without looking. Generated with Web Audio — no audio files to ship.
 *
 * @module
 */

/** The cues Jarvis can play. */
export type Earcon = 'wake' | 'listen-end' | 'notify' | 'timer' | 'error';

interface Tone {
  /** Frequency in Hz. */
  readonly freq: number;
  /** Start offset in seconds. */
  readonly at: number;
  /** Length in seconds. */
  readonly length: number;
  /** Peak gain (0–1). */
  readonly gain: number;
}

/** Tone sequences per earcon: rising = attention, falling = done. */
export const EARCON_TONES: Readonly<Record<Earcon, readonly Tone[]>> = {
  wake: [
    { freq: 880, at: 0, length: 0.12, gain: 0.07 },
    { freq: 1318.5, at: 0.07, length: 0.18, gain: 0.06 },
  ],
  'listen-end': [
    { freq: 1174.7, at: 0, length: 0.1, gain: 0.05 },
    { freq: 784, at: 0.06, length: 0.16, gain: 0.045 },
  ],
  notify: [
    { freq: 987.8, at: 0, length: 0.14, gain: 0.06 },
    { freq: 1318.5, at: 0.12, length: 0.14, gain: 0.055 },
    { freq: 1568, at: 0.24, length: 0.24, gain: 0.05 },
  ],
  // Three soft double-chimes: insistent enough to hear from the kitchen.
  timer: [0, 0.45, 0.9].flatMap((at) => [
    { freq: 1318.5, at, length: 0.16, gain: 0.07 },
    { freq: 1760, at: at + 0.14, length: 0.22, gain: 0.065 },
  ]),
  error: [
    { freq: 392, at: 0, length: 0.16, gain: 0.06 },
    { freq: 311.1, at: 0.12, length: 0.24, gain: 0.06 },
  ],
};

/**
 * The cue for a server notification, and whether it should sound even when
 * notification chimes are muted (focus mode): a timer you can't hear is useless.
 */
export function earconForNotification(kind: string): { earcon: Earcon; always: boolean } {
  return kind === 'timer' ? { earcon: 'timer', always: true } : { earcon: 'notify', always: false };
}

/** Plays earcons on a shared AudioContext. */
export class EarconPlayer {
  readonly #context: AudioContext;
  enabled = true;

  constructor(context: AudioContext) {
    this.#context = context;
  }

  /** Play a cue (no-op when disabled). */
  play(earcon: Earcon): void {
    if (!this.enabled || this.#context.state !== 'running') return;
    const start = this.#context.currentTime + 0.01;
    for (const tone of EARCON_TONES[earcon]) this.#tone(tone, start);
  }

  #tone({ freq, at, length, gain }: Tone, start: number): void {
    const ctx = this.#context;
    const osc = ctx.createOscillator();
    const amp = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.value = freq;
    // Soft attack and exponential release: a glassy "ping", never a click.
    const t0 = start + at;
    amp.gain.setValueAtTime(0, t0);
    amp.gain.linearRampToValueAtTime(gain, t0 + 0.012);
    amp.gain.exponentialRampToValueAtTime(0.0001, t0 + length);
    osc.connect(amp).connect(ctx.destination);
    osc.start(t0);
    osc.stop(t0 + length + 0.02);
  }
}

/**
 * Which earcon (if any) marks a state transition.
 *
 * - entering `listening` → "wake" (Jarvis is all ears)
 * - `listening` → `thinking` → "listen-end" (got it)
 */
export function earconForTransition(from: string, to: string): Earcon | null {
  if (to === 'listening' && from !== 'listening') return 'wake';
  if (from === 'listening' && to === 'thinking') return 'listen-end';
  return null;
}
