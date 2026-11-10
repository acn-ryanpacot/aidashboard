/**
 * Microphone capture: getUserMedia → AudioWorklet (16 kHz PCM16 frames).
 *
 * @module
 */

/** Options for {@link MicrophoneCapture.start}. */
export interface CaptureOptions {
  /** Target sample rate expected by the server. */
  readonly sampleRate: number;
  /** Samples per emitted frame. */
  readonly frameSamples: number;
  /** Receives each encoded frame. */
  readonly onFrame: (frame: ArrayBuffer) => void;
}

const WORKLET_URL = '/worklets/pcm-capture.js';

/**
 * Captures the default microphone into an {@link AnalyserNode} (for the
 * visualiser) and an AudioWorklet that emits fixed-size PCM16 frames.
 */
export class MicrophoneCapture {
  readonly analyser: AnalyserNode;
  readonly #context: AudioContext;
  #stream: MediaStream | null = null;
  #source: MediaStreamAudioSourceNode | null = null;
  #worklet: AudioWorkletNode | null = null;
  #sink: GainNode | null = null;

  constructor(context: AudioContext) {
    this.#context = context;
    this.analyser = context.createAnalyser();
    this.analyser.fftSize = 256;
    this.analyser.smoothingTimeConstant = 0.75;
  }

  /** Whether the microphone is live. */
  get active(): boolean {
    return this.#stream !== null;
  }

  /**
   * Ask for microphone permission and start emitting frames.
   *
   * @throws DOMException if the user denies permission or no mic exists.
   */
  async start(options: CaptureOptions): Promise<void> {
    if (this.active) return;
    await this.#context.audioWorklet.addModule(WORKLET_URL);
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });

    const source = this.#context.createMediaStreamSource(stream);
    const worklet = new AudioWorkletNode(this.#context, 'pcm-capture', {
      numberOfInputs: 1,
      numberOfOutputs: 1,
      channelCount: 1,
      processorOptions: {
        targetSampleRate: options.sampleRate,
        frameSamples: options.frameSamples,
      },
    });
    worklet.port.onmessage = (event: MessageEvent<ArrayBuffer>) => options.onFrame(event.data);

    // Keep the worklet in the rendering graph without making the mic audible.
    const sink = this.#context.createGain();
    sink.gain.value = 0;
    source.connect(this.analyser);
    source.connect(worklet).connect(sink).connect(this.#context.destination);

    this.#stream = stream;
    this.#source = source;
    this.#worklet = worklet;
    this.#sink = sink;
  }

  /** Release the microphone. */
  stop(): void {
    this.#worklet?.port.close();
    this.#worklet?.disconnect();
    this.#sink?.disconnect();
    this.#source?.disconnect();
    this.#stream?.getTracks().forEach((track) => track.stop());
    this.#stream = null;
    this.#source = null;
    this.#worklet = null;
    this.#sink = null;
  }
}
