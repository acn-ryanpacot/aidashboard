/**
 * Canvas renderer for the assistant "core" — the reactive orb at the centre
 * of the HUD. Pure drawing code with no React, so it can be profiled and
 * reasoned about in isolation.
 *
 * Visual layers, back to front:
 *  1. ambient glow that breathes with the audio level
 *  2. HUD furniture: compass ticks, dashed orbit, rotating arc segments
 *  3. radial spectrum bars driven by the AnalyserNode (mirrored left/right)
 *  4. a liquid membrane that ripples with each syllable
 *  5. the luminous core
 *
 * @module
 */
import { perceptualLevel } from '../../core/voice/captions';
import type { AssistantState } from '../../core/voice/protocol';

type Rgb = readonly [number, number, number];

/** Accent colour per state; the renderer cross-fades between them. */
const STATE_COLOURS: Record<AssistantState, Rgb> = {
  idle: [94, 231, 255],
  listening: [120, 255, 226],
  thinking: [255, 196, 92],
  speaking: [150, 238, 255],
};

/** Overall brightness per state. */
const STATE_INTENSITY: Record<AssistantState, number> = {
  idle: 0.55,
  listening: 0.9,
  thinking: 0.8,
  speaking: 1,
};

const BAR_COUNT = 128;
const TICK_COUNT = 72;
const TAU = Math.PI * 2;

const rgba = ([r, g, b]: Rgb, a: number) => `rgba(${r | 0}, ${g | 0}, ${b | 0}, ${a.toFixed(3)})`;
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

/** Inputs for one animation frame. */
export interface OrbFrame {
  /** Seconds since the renderer started. */
  readonly time: number;
  readonly state: AssistantState;
  /** Byte frequency data from an AnalyserNode, or `null` when silent. */
  readonly spectrum: Uint8Array | null;
}

/** Stateful renderer: keeps smoothed values between frames for fluid motion. */
export class OrbRenderer {
  readonly #bars = new Float32Array(BAR_COUNT);
  #level = 0;
  #colour: [number, number, number] = [...STATE_COLOURS.idle];
  #intensity = STATE_INTENSITY.idle;
  #spin = 0;
  #lastTime = 0;

  /**
   * Draw one frame.
   *
   * @param ctx - 2D context of a canvas already scaled to device pixels.
   * @param width - Canvas width in device pixels.
   * @param height - Canvas height in device pixels.
   */
  draw(ctx: CanvasRenderingContext2D, width: number, height: number, frame: OrbFrame): void {
    const dt = Math.min(0.05, Math.max(0, frame.time - this.#lastTime));
    this.#lastTime = frame.time;
    this.#update(frame, dt);

    const cx = width / 2;
    const cy = height / 2;
    const radius = Math.min(width, height) * 0.2;
    const colour = this.#colour;
    const level = this.#level;
    const intensity = this.#intensity;
    const breath = 0.5 + 0.5 * Math.sin(frame.time * 1.3);

    ctx.clearRect(0, 0, width, height);
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';

    this.#drawGlow(ctx, cx, cy, radius, colour, intensity * (0.6 + level * 0.9 + breath * 0.1));
    this.#drawFurniture(ctx, cx, cy, radius, colour, intensity, frame);
    this.#drawSpectrum(ctx, cx, cy, radius, colour, intensity);
    this.#drawMembrane(ctx, cx, cy, radius, colour, intensity, frame.time);
    this.#drawCore(ctx, cx, cy, radius * (0.56 + level * 0.14 + breath * 0.015), colour, intensity);

    ctx.restore();
  }

  #update(frame: OrbFrame, dt: number): void {
    // Colour and brightness ease toward the target state (~250 ms).
    const ease = 1 - Math.exp(-dt * 9);
    const target = STATE_COLOURS[frame.state];
    for (let i = 0; i < 3; i++) this.#colour[i] = lerp(this.#colour[i] ?? 0, target[i] ?? 0, ease);
    this.#intensity = lerp(this.#intensity, STATE_INTENSITY[frame.state], ease);

    // Audio level: fast attack, slower release → a visible "bounce" per word.
    const spectrum = frame.spectrum;
    let raw = 0;
    if (spectrum) {
      let sum = 0;
      const upper = Math.min(48, spectrum.length);
      for (let i = 2; i < upper; i++) sum += spectrum[i] ?? 0;
      raw = perceptualLevel(sum / ((upper - 2) * 255), 3.2);
    }
    this.#level = lerp(this.#level, raw, raw > this.#level ? 0.45 : 0.1);

    const spinSpeed = frame.state === 'thinking' ? 2.4 : frame.state === 'idle' ? 0.12 : 0.35;
    this.#spin += dt * spinSpeed;

    // Spectrum bars, mirrored so the shape is symmetric about the vertical axis.
    const half = BAR_COUNT / 2;
    for (let i = 0; i < BAR_COUNT; i++) {
      const k = i < half ? i : BAR_COUNT - 1 - i;
      let value = 0;
      if (spectrum) {
        const bin = 2 + Math.floor((k / half) * Math.min(56, spectrum.length - 3));
        value = ((spectrum[bin] ?? 0) / 255) ** 1.4;
      }
      const idle = 0.035 + 0.025 * Math.sin(frame.time * 1.6 + i * 0.35);
      const sweep =
        frame.state === 'thinking'
          ? 0.35 * Math.max(0, Math.cos((i / BAR_COUNT) * TAU - this.#spin * 1.5)) ** 12
          : 0;
      const target = Math.max(value, idle + sweep);
      const current = this.#bars[i] ?? 0;
      this.#bars[i] = lerp(current, target, target > current ? 0.5 : 0.14);
    }
  }

  #drawGlow(c: CanvasRenderingContext2D, x: number, y: number, r: number, rgb: Rgb, a: number) {
    const g = c.createRadialGradient(x, y, r * 0.2, x, y, r * 3.2);
    g.addColorStop(0, rgba(rgb, 0.22 * a));
    g.addColorStop(0.35, rgba(rgb, 0.08 * a));
    g.addColorStop(1, rgba(rgb, 0));
    c.fillStyle = g;
    c.fillRect(x - r * 3.2, y - r * 3.2, r * 6.4, r * 6.4);
  }

  #drawFurniture(
    c: CanvasRenderingContext2D,
    x: number,
    y: number,
    r: number,
    rgb: Rgb,
    a: number,
    frame: OrbFrame,
  ) {
    const unit = r / 120;

    // Compass ticks.
    for (let i = 0; i < TICK_COUNT; i++) {
      const angle = (i / TICK_COUNT) * TAU;
      const major = i % 6 === 0;
      const inner = r * 2.06;
      const outer = inner + (major ? 10 : 4) * unit;
      c.beginPath();
      c.moveTo(x + Math.cos(angle) * inner, y + Math.sin(angle) * inner);
      c.lineTo(x + Math.cos(angle) * outer, y + Math.sin(angle) * outer);
      c.strokeStyle = rgba(rgb, (major ? 0.28 : 0.12) * a);
      c.lineWidth = Math.max(1, unit * 1.2);
      c.stroke();
    }

    // Dashed orbit.
    c.save();
    c.translate(x, y);
    c.rotate(this.#spin * 0.4);
    c.setLineDash([2 * unit, 9 * unit]);
    c.beginPath();
    c.arc(0, 0, r * 1.82, 0, TAU);
    c.strokeStyle = rgba(rgb, 0.22 * a);
    c.lineWidth = Math.max(1, unit * 1.4);
    c.stroke();
    c.restore();

    // Counter-rotating arc segments.
    c.save();
    c.translate(x, y);
    c.rotate(-this.#spin);
    c.lineCap = 'round';
    for (let i = 0; i < 3; i++) {
      const start = (i / 3) * TAU;
      c.beginPath();
      c.arc(0, 0, r * 1.95, start, start + TAU / 9);
      c.strokeStyle = rgba(rgb, 0.4 * a);
      c.lineWidth = Math.max(1.5, unit * 2.4);
      c.stroke();
    }
    c.restore();

    // Thin inner ring that frames the spectrum.
    c.beginPath();
    c.arc(x, y, r * 1.02, 0, TAU);
    c.strokeStyle = rgba(rgb, 0.3 * a);
    c.lineWidth = Math.max(1, unit);
    c.stroke();

    // "Thinking" comet that chases around the ring.
    if (frame.state === 'thinking') {
      const head = this.#spin * 1.5;
      for (let i = 0; i < 24; i++) {
        const t = i / 24;
        c.beginPath();
        c.arc(x, y, r * 1.02, head - t * 1.2 - 0.06, head - t * 1.2);
        c.strokeStyle = rgba(rgb, (1 - t) * 0.9 * a);
        c.lineWidth = Math.max(1.5, unit * 3 * (1 - t));
        c.stroke();
      }
    }
  }

  #drawSpectrum(c: CanvasRenderingContext2D, x: number, y: number, r: number, rgb: Rgb, a: number) {
    const inner = r * 1.1;
    const maxLength = r * 0.62;
    const width = Math.max(1.5, ((TAU * inner) / BAR_COUNT) * 0.42);
    c.lineCap = 'round';
    c.lineWidth = width;
    for (let i = 0; i < BAR_COUNT; i++) {
      const value = this.#bars[i] ?? 0;
      const angle = (i / BAR_COUNT) * TAU - Math.PI / 2;
      const length = r * 0.04 + value * maxLength;
      const cos = Math.cos(angle);
      const sin = Math.sin(angle);
      c.beginPath();
      c.moveTo(x + cos * inner, y + sin * inner);
      c.lineTo(x + cos * (inner + length), y + sin * (inner + length));
      c.strokeStyle = rgba(rgb, (0.25 + value * 0.75) * a);
      c.stroke();
    }
  }

  #drawMembrane(
    c: CanvasRenderingContext2D,
    x: number,
    y: number,
    r: number,
    rgb: Rgb,
    a: number,
    time: number,
  ) {
    const base = r * 0.9;
    const amp = r * (0.015 + this.#level * 0.09);
    const steps = 160;
    for (let layer = 0; layer < 2; layer++) {
      c.beginPath();
      for (let i = 0; i <= steps; i++) {
        const angle = (i / steps) * TAU;
        const wobble =
          Math.sin(angle * 3 + time * 2.1 + layer) * 0.5 +
          Math.sin(angle * 5 - time * 1.7 + layer * 2) * 0.3 +
          Math.sin(angle * 8 + time * 3.3) * 0.2;
        const rr = base + layer * r * 0.04 + wobble * amp;
        const px = x + Math.cos(angle) * rr;
        const py = y + Math.sin(angle) * rr;
        if (i === 0) c.moveTo(px, py);
        else c.lineTo(px, py);
      }
      c.closePath();
      c.strokeStyle = rgba(rgb, (layer === 0 ? 0.55 : 0.25) * a);
      c.lineWidth = Math.max(1, r / 110);
      c.stroke();
    }
  }

  #drawCore(c: CanvasRenderingContext2D, x: number, y: number, r: number, rgb: Rgb, a: number) {
    const g = c.createRadialGradient(x, y, 0, x, y, r);
    g.addColorStop(0, `rgba(255, 255, 255, ${(0.95 * a).toFixed(3)})`);
    g.addColorStop(0.18, rgba(rgb, 0.9 * a));
    g.addColorStop(0.55, rgba(rgb, 0.28 * a));
    g.addColorStop(1, rgba(rgb, 0));
    c.fillStyle = g;
    c.beginPath();
    c.arc(x, y, r, 0, TAU);
    c.fill();

    c.beginPath();
    c.arc(x, y, r * 0.46, 0, TAU);
    c.strokeStyle = rgba(rgb, 0.45 * a);
    c.lineWidth = Math.max(1, r / 90);
    c.stroke();
  }
}
