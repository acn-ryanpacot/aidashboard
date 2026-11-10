// @ts-check
/**
 * AudioWorklet that converts microphone audio into the core service's input
 * format: 16 kHz, mono, 16-bit PCM, in fixed frames of `frameSamples` samples
 * (1280 = 80 ms, which is what openWakeWord expects).
 *
 * Resampling uses a fractional-phase box filter: each output sample is the
 * mean of the input samples it covers. That doubles as a cheap anti-aliasing
 * low-pass, which is plenty for speech recognition.
 *
 * This file is plain JavaScript (served from /public) because audio worklets
 * are loaded by URL at runtime, outside the bundler.
 */

/* global sampleRate, registerProcessor, AudioWorkletProcessor */

class PcmCaptureProcessor extends AudioWorkletProcessor {
  /** @param {{ processorOptions?: { targetSampleRate?: number, frameSamples?: number } }} options */
  constructor(options) {
    super();
    const { targetSampleRate = 16000, frameSamples = 1280 } = options.processorOptions ?? {};
    /** Input samples per output sample (e.g. 3.0 for 48 kHz → 16 kHz). */
    this.ratio = sampleRate / targetSampleRate;
    this.frameSamples = frameSamples;
    this.frame = new Int16Array(frameSamples);
    this.frameIndex = 0;
    this.phase = 0;
    this.sum = 0;
    this.count = 0;
  }

  /** @param {Float32Array[][]} inputs */
  process(inputs) {
    const channel = inputs[0]?.[0];
    if (!channel) return true;

    for (let i = 0; i < channel.length; i++) {
      this.sum += channel[i];
      this.count++;
      this.phase += 1;
      if (this.phase < this.ratio) continue;

      this.phase -= this.ratio;
      const sample = Math.max(-1, Math.min(1, this.sum / this.count));
      this.sum = 0;
      this.count = 0;
      this.frame[this.frameIndex++] = Math.round(sample * 0x7fff);

      if (this.frameIndex === this.frameSamples) {
        const out = this.frame.slice(0);
        this.port.postMessage(out.buffer, [out.buffer]);
        this.frameIndex = 0;
      }
    }
    return true;
  }
}

registerProcessor('pcm-capture', PcmCaptureProcessor);
