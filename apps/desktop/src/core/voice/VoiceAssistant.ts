/**
 * The voice assistant controller: glues the WebSocket client, microphone,
 * speech player and state store together. Contains no React code.
 *
 * @module
 */
import { type AssistantStoreApi, createAssistantStore } from '../../state/assistantStore';
import type { ActiveCaption } from './SpeechPlayer';
import { MicrophoneCapture } from './MicrophoneCapture';
import type { ServerMessage, SpeechSegmentMessage } from './protocol';
import { SpeechPlayer } from './SpeechPlayer';
import { VoiceClient } from './VoiceClient';

const DEFAULT_SAMPLE_RATE = 16_000;
const DEFAULT_FRAME_SAMPLES = 1_280;

/**
 * Facade over the whole client-side voice pipeline.
 *
 * Lifecycle: {@link start} (connect) → {@link engage} (on a user gesture —
 * browsers only allow audio after one) → … → {@link dispose}.
 */
export class VoiceAssistant {
  /** Observable state for the UI. */
  readonly store: AssistantStoreApi = createAssistantStore();

  readonly #url: string;
  #client: VoiceClient | null = null;
  #context: AudioContext | null = null;
  #mic: MicrophoneCapture | null = null;
  #player: SpeechPlayer | null = null;

  constructor(url: string) {
    this.#url = url;
  }

  /** Connect to the core service (idempotent). */
  start(): void {
    if (this.#client) return;
    this.store.getState().setConnection('connecting');
    this.#client = new VoiceClient(this.#url, {
      onOpen: () => this.store.getState().setConnection('online'),
      onClose: () => {
        this.#player?.stop();
        this.store.getState().setConnection('offline');
      },
      onMessage: (message) => this.#handleMessage(message),
      onSpeech: (segment, wav) => this.#handleSpeech(segment, wav),
    });
    this.#client.connect();
  }

  /** Disconnect and release audio hardware. */
  dispose(): void {
    this.#client?.dispose();
    this.#client = null;
    this.#mic?.stop();
    this.#player?.stop();
    void this.#context?.close();
    this.#context = null;
    this.#mic = null;
    this.#player = null;
    this.store.getState().setEngaged(false);
  }

  /**
   * Unlock audio. Must be called from a user gesture (click / key press).
   *
   * @param withMicrophone - Also start listening for the wake word.
   */
  async engage(withMicrophone: boolean): Promise<void> {
    if (!this.#context) {
      this.#context = new AudioContext({ latencyHint: 'interactive' });
      this.#player = new SpeechPlayer(this.#context, (segmentId) =>
        this.#client?.send({ type: 'playback_ended', segment_id: segmentId }),
      );
    }
    await this.#context.resume();
    this.store.getState().setEngaged(true);
    if (withMicrophone) await this.enableMicrophone();
  }

  /** Start streaming the microphone (asks for permission the first time). */
  async enableMicrophone(): Promise<void> {
    if (!this.#context) return;
    const capabilities = this.store.getState().capabilities;
    this.#mic ??= new MicrophoneCapture(this.#context);
    try {
      await this.#mic.start({
        sampleRate: capabilities?.input_sample_rate ?? DEFAULT_SAMPLE_RATE,
        frameSamples: capabilities?.input_frame_samples ?? DEFAULT_FRAME_SAMPLES,
        onFrame: (frame) => this.#handleMicFrame(frame),
      });
      this.store.getState().setMic(true);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      this.store.getState().setMic(false, `Microphone unavailable: ${message}`);
    }
  }

  /** Stop streaming the microphone. */
  disableMicrophone(): void {
    this.#mic?.stop();
    this.store.getState().setMic(false);
  }

  /** Wake the assistant manually (same as saying the wake word). */
  activate(): void {
    this.#player?.stop();
    this.#client?.send({ type: 'activate' });
  }

  /** Ask a typed question. */
  ask(text: string): void {
    const trimmed = text.trim();
    if (!trimmed) return;
    this.#player?.stop();
    this.#client?.send({ type: 'text_query', text: trimmed });
  }

  /** Interrupt the current answer. */
  cancel(): void {
    this.#player?.stop();
    this.#client?.send({ type: 'cancel' });
  }

  /**
   * The audio the visualiser should react to: Jarvis's voice while speaking,
   * the user's voice while listening, otherwise nothing.
   */
  levelSource(): AnalyserNode | null {
    switch (this.store.getState().state) {
      case 'speaking':
        return this.#player?.analyser ?? null;
      case 'listening':
        return this.#mic?.active ? this.#mic.analyser : null;
      default:
        return null;
    }
  }

  /** The caption for what is being said right now. */
  activeCaption(): ActiveCaption | null {
    return this.#player?.activeCaption() ?? null;
  }

  #handleMicFrame(frame: ArrayBuffer): void {
    const { state, capabilities } = this.store.getState();
    const wantsAudio =
      state === 'listening' || (state === 'idle' && capabilities?.wake_word_enabled);
    if (wantsAudio) this.#client?.sendAudio(frame);
  }

  #handleMessage(message: ServerMessage): void {
    const store = this.store.getState();
    switch (message.type) {
      case 'ready':
        store.setCapabilities(message);
        break;
      case 'state':
        store.setState(message.state);
        break;
      case 'transcript':
        store.addMessage('user', message.text);
        break;
      case 'assistant_delta':
        store.appendAssistant(message.text);
        break;
      case 'turn_complete':
        store.completeAssistant(message.text);
        break;
      case 'error':
        store.addMessage('system', message.message, true);
        break;
      case 'wake':
      case 'speech_segment':
        break;
    }
  }

  #handleSpeech(segment: SpeechSegmentMessage, wav: ArrayBuffer): void {
    if (segment.kind === 'greeting') this.store.getState().addMessage('assistant', segment.text);
    if (this.#player) {
      void this.#player.enqueue(segment, wav);
    } else {
      // Audio is locked (not engaged yet): acknowledge so the server moves on.
      this.#client?.send({ type: 'playback_ended', segment_id: segment.segment_id });
    }
  }
}
