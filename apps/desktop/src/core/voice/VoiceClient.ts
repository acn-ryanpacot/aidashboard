/**
 * Resilient WebSocket client for the core service's `/ws/voice` endpoint.
 *
 * @module
 */
import {
  type ClientMessage,
  type ServerMessage,
  type SpeechSegmentMessage,
  parseServerMessage,
} from './protocol';

/** Callbacks a {@link VoiceClient} reports to. */
export interface VoiceClientHandlers {
  onOpen(): void;
  onClose(): void;
  /** Any JSON message except `speech_segment` (see {@link onSpeech}). */
  onMessage(message: ServerMessage): void;
  /** A speech segment header paired with its WAV payload. */
  onSpeech(segment: SpeechSegmentMessage, wav: ArrayBuffer): void;
}

/** Reconnect delays grow exponentially up to this cap (ms). */
const MAX_BACKOFF_MS = 8_000;
/** Drop microphone frames instead of queueing if the socket backs up (bytes). */
const MAX_BUFFERED_AUDIO = 64 * 1024;

/**
 * Owns the WebSocket: reconnects with exponential backoff, pairs each
 * `speech_segment` header with the binary WAV frame that follows it, and
 * exposes typed send helpers.
 */
export class VoiceClient {
  readonly #url: string;
  readonly #handlers: VoiceClientHandlers;
  #socket: WebSocket | null = null;
  #pendingSegment: SpeechSegmentMessage | null = null;
  #retryTimer: ReturnType<typeof setTimeout> | null = null;
  #attempt = 0;
  #disposed = false;

  constructor(url: string, handlers: VoiceClientHandlers) {
    this.#url = url;
    this.#handlers = handlers;
  }

  /** Whether the socket is currently open. */
  get isOpen(): boolean {
    return this.#socket?.readyState === WebSocket.OPEN;
  }

  /** Open the connection (and keep re-opening it until {@link dispose}). */
  connect(): void {
    if (this.#disposed || this.#socket) return;
    const socket = new WebSocket(this.#url);
    socket.binaryType = 'arraybuffer';
    socket.onopen = () => {
      this.#attempt = 0;
      this.#handlers.onOpen();
    };
    socket.onmessage = (event: MessageEvent<string | ArrayBuffer>) => this.#receive(event.data);
    socket.onclose = () => {
      this.#socket = null;
      this.#pendingSegment = null;
      this.#handlers.onClose();
      this.#scheduleReconnect();
    };
    this.#socket = socket;
  }

  /** Send a JSON control message. Silently dropped while disconnected. */
  send(message: ClientMessage): void {
    if (this.isOpen) this.#socket?.send(JSON.stringify(message));
  }

  /** Stream one microphone frame (16 kHz mono PCM16). */
  sendAudio(frame: ArrayBuffer): void {
    const socket = this.#socket;
    if (socket?.readyState === WebSocket.OPEN && socket.bufferedAmount < MAX_BUFFERED_AUDIO) {
      socket.send(frame);
    }
  }

  /** Close for good; no further reconnects. */
  dispose(): void {
    this.#disposed = true;
    if (this.#retryTimer) clearTimeout(this.#retryTimer);
    const socket = this.#socket;
    this.#socket = null;
    if (!socket) return;
    socket.onclose = null;
    socket.onmessage = null;
    if (socket.readyState === WebSocket.CONNECTING) {
      // Closing mid-handshake logs a browser warning; close once it opens.
      socket.onopen = () => socket.close();
    } else {
      socket.onopen = null;
      socket.close();
    }
  }

  #receive(data: string | ArrayBuffer): void {
    if (typeof data === 'string') {
      const message = parseServerMessage(data);
      if (!message) return;
      if (message.type === 'speech_segment') {
        this.#pendingSegment = message;
      } else {
        this.#handlers.onMessage(message);
      }
      return;
    }
    const segment = this.#pendingSegment;
    this.#pendingSegment = null;
    if (segment) this.#handlers.onSpeech(segment, data);
  }

  #scheduleReconnect(): void {
    if (this.#disposed) return;
    const delay = Math.min(MAX_BACKOFF_MS, 500 * 2 ** this.#attempt);
    this.#attempt += 1;
    this.#retryTimer = setTimeout(() => this.connect(), delay);
  }
}
