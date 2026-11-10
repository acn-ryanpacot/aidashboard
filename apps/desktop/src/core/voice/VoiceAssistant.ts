/**
 * The voice assistant controller: glues the WebSocket client, microphone,
 * speech player, earcons and state store together. Contains no React code.
 *
 * @module
 */
import { type AssistantStoreApi, createAssistantStore } from '../../state/assistantStore';
import { EarconPlayer, earconForTransition } from '../audio/earcons';
import { MicrophoneCapture } from './MicrophoneCapture';
import type { AssistantState, ServerMessage, SpeechSegmentMessage } from './protocol';
import { type ActiveCaption, SpeechPlayer } from './SpeechPlayer';
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
  #earcons: EarconPlayer | null = null;

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
    this.#earcons = null;
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
      this.#earcons = new EarconPlayer(this.#context);
      this.#earcons.enabled = this.store.getState().soundsEnabled;
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

  /** Turn UI sounds on or off (persisted). */
  setSoundsEnabled(enabled: boolean): void {
    this.store.getState().setSoundsEnabled(enabled);
    if (this.#earcons) this.#earcons.enabled = enabled;
  }

  /** Wake the assistant manually (same as saying the wake word). */
  activate(): void {
    this.#player?.stop();
    this.#client?.send({ type: 'activate' });
  }

  /** Push-to-talk: start listening right away, without the greeting. */
  listen(): void {
    this.#player?.stop();
    this.#client?.send({ type: 'listen' });
  }

  /** Ask a typed question. */
  ask(text: string): void {
    const trimmed = text.trim();
    if (!trimmed) return;
    this.#player?.stop();
    this.#client?.send({ type: 'text_query', text: trimmed });
  }

  /** Interrupt the current answer (or enrollment). */
  cancel(): void {
    this.#player?.stop();
    this.#client?.send({ type: 'cancel' });
  }

  /** Begin voice-ID enrollment (the user speaks a few sentences). */
  enrollVoice(): void {
    this.#player?.stop();
    this.#client?.send({ type: 'enroll_voice' });
  }

  /** Close the enrollment overlay after it has finished. */
  dismissEnrollment(): void {
    this.store.getState().setEnrollment(null);
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
    if (
      wantsAudio(state, capabilities?.wake_word_enabled ?? false, capabilities?.barge_in ?? 'off')
    ) {
      this.#client?.sendAudio(frame);
    }
  }

  #handleMessage(message: ServerMessage): void {
    const store = this.store.getState();
    switch (message.type) {
      case 'ready':
        store.setCapabilities(message);
        break;
      case 'state': {
        const cue = earconForTransition(store.state, message.state);
        if (cue) this.#earcons?.play(cue);
        store.setState(message.state);
        break;
      }
      case 'interrupted':
        this.#player?.stop();
        break;
      case 'transcript':
        store.addMessage('user', message.text);
        break;
      case 'assistant_delta':
        store.setActiveTool(null);
        store.appendAssistant(message.text);
        break;
      case 'tool':
        store.setActiveTool(message.label);
        break;
      case 'turn_complete':
        store.completeAssistant(message.text);
        break;
      case 'metrics':
        store.setMetrics(message);
        break;
      case 'speaker_rejected':
        store.markRejected();
        this.#earcons?.play('error');
        break;
      case 'enrollment':
        store.setEnrollment(message);
        if (message.status === 'complete') {
          this.#earcons?.play('notify');
          const caps = store.capabilities;
          if (caps) store.setCapabilities({ ...caps, speaker_enrolled: true });
        }
        break;
      case 'notification':
        store.addMessage('notice', message.text);
        this.#earcons?.play('notify');
        break;
      case 'data_changed':
        store.bumpData(message.topic);
        break;
      case 'error':
        store.addMessage('system', message.message, true);
        this.#earcons?.play('error');
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

/**
 * Whether microphone frames are useful to the server right now.
 *
 * - idle: only if a wake word is listening;
 * - listening: always;
 * - thinking / speaking: only for barge-in.
 */
export function wantsAudio(
  state: AssistantState,
  wakeWordEnabled: boolean,
  bargeIn: 'off' | 'wake_word' | 'voice',
): boolean {
  switch (state) {
    case 'idle':
      return wakeWordEnabled;
    case 'listening':
      return true;
    default:
      return bargeIn === 'voice' || (bargeIn === 'wake_word' && wakeWordEnabled);
  }
}
