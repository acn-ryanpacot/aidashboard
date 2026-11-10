/**
 * TypeScript mirror of the `/ws/voice` wire protocol.
 *
 * Source of truth: `services/core/src/jarvis_core/api/protocol.py`.
 * Keep both files in sync (see docs/architecture/voice-protocol.md).
 *
 * @module
 */

/** What the assistant is doing. Drives the orb animation. */
export type AssistantState = 'idle' | 'listening' | 'thinking' | 'speaking';

/** Timing of one spoken word, in seconds from the start of its segment. */
export interface WordTiming {
  readonly word: string;
  readonly start: number;
  readonly end: number;
}

// ------------------------------------------------------------ server → client

export interface ReadyMessage {
  readonly type: 'ready';
  readonly protocol_version: number;
  readonly assistant_name: string;
  readonly user_name: string;
  readonly wake_word_enabled: boolean;
  readonly wake_model: string | null;
  readonly speech_input_enabled: boolean;
  readonly speech_output_enabled: boolean;
  readonly input_sample_rate: number;
  readonly input_frame_samples: number;
}

export interface StateMessage {
  readonly type: 'state';
  readonly state: AssistantState;
}

export interface WakeMessage {
  readonly type: 'wake';
}

export interface TranscriptMessage {
  readonly type: 'transcript';
  readonly text: string;
}

export interface AssistantDeltaMessage {
  readonly type: 'assistant_delta';
  readonly text: string;
}

/** Header describing the WAV binary frame that immediately follows it. */
export interface SpeechSegmentMessage {
  readonly type: 'speech_segment';
  readonly segment_id: string;
  readonly kind: 'greeting' | 'answer';
  readonly text: string;
  readonly duration: number;
  readonly words: readonly WordTiming[];
}

export interface TurnCompleteMessage {
  readonly type: 'turn_complete';
  readonly text: string;
}

export interface ErrorMessage {
  readonly type: 'error';
  readonly message: string;
}

export type ServerMessage =
  | ReadyMessage
  | StateMessage
  | WakeMessage
  | TranscriptMessage
  | AssistantDeltaMessage
  | SpeechSegmentMessage
  | TurnCompleteMessage
  | ErrorMessage;

// ------------------------------------------------------------ client → server

export type ClientMessage =
  | { readonly type: 'activate' }
  | { readonly type: 'text_query'; readonly text: string }
  | { readonly type: 'playback_ended'; readonly segment_id: string }
  | { readonly type: 'cancel' };

const SERVER_MESSAGE_TYPES = new Set<ServerMessage['type']>([
  'ready',
  'state',
  'wake',
  'transcript',
  'assistant_delta',
  'speech_segment',
  'turn_complete',
  'error',
]);

/**
 * Parse a JSON text frame from the server.
 *
 * @returns The message, or `null` if it is malformed or of an unknown type
 *   (unknown types are ignored for forward compatibility).
 */
export function parseServerMessage(raw: string): ServerMessage | null {
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    return null;
  }
  if (typeof value !== 'object' || value === null || !('type' in value)) return null;
  const { type } = value as { type: unknown };
  if (typeof type !== 'string' || !SERVER_MESSAGE_TYPES.has(type as ServerMessage['type'])) {
    return null;
  }
  return value as ServerMessage;
}

/**
 * Turn an openWakeWord model name or path into the phrase to say.
 *
 * @example
 * ```ts
 * wakePhrase('hey_jarvis');                  // "Hey Jarvis"
 * wakePhrase('C:/models/hello_jarvis.onnx'); // "Hello Jarvis"
 * ```
 */
export function wakePhrase(model: string | null): string | null {
  if (!model) return null;
  const base = model.split(/[\\/]/).pop() ?? model;
  const words = base
    .replace(/\.(onnx|tflite)$/i, '')
    .replace(/_v\d+(\.\d+)*$/i, '')
    .split(/[_\-\s]+/)
    .filter(Boolean);
  if (words.length === 0) return null;
  return words.map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()).join(' ');
}
