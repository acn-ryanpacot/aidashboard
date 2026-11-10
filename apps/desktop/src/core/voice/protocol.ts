/**
 * TypeScript mirror of the `/ws/voice` wire protocol (version 3).
 *
 * Source of truth: `services/core/src/jarvis_core/api/protocol.py`.
 * Keep both files in sync (see docs/architecture/voice-protocol.md).
 *
 * @module
 */

/** Protocol version this client implements. */
export const PROTOCOL_VERSION = 3;

/** What the assistant is doing. Drives the orb animation. */
export type AssistantState = 'idle' | 'listening' | 'thinking' | 'speaking';

/** How the user may interrupt Jarvis. */
export type BargeInMode = 'off' | 'wake_word' | 'voice';

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
  readonly barge_in: BargeInMode;
  /** Continuous speech the client must hear before sending `barge_in`. */
  readonly barge_in_min_speech_ms: number;
  readonly speaker_verification_enabled: boolean;
  readonly speaker_enrolled: boolean;
  readonly tools: readonly string[];
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

/** Stop playback immediately: the user cut Jarvis off. */
export interface InterruptedMessage {
  readonly type: 'interrupted';
}

export interface TranscriptMessage {
  readonly type: 'transcript';
  readonly text: string;
}

export interface AssistantDeltaMessage {
  readonly type: 'assistant_delta';
  readonly text: string;
}

/** The brain is running a tool. */
export interface ToolMessage {
  readonly type: 'tool';
  readonly name: string;
  readonly label: string;
}

/** Header describing the WAV binary frame that immediately follows it. */
export interface SpeechSegmentMessage {
  readonly type: 'speech_segment';
  readonly segment_id: string;
  readonly kind: 'greeting' | 'answer' | 'announcement';
  readonly text: string;
  readonly duration: number;
  readonly words: readonly WordTiming[];
}

export interface TurnCompleteMessage {
  readonly type: 'turn_complete';
  readonly text: string;
}

/** Latency breakdown of the last turn, in milliseconds. */
export interface MetricsMessage {
  readonly type: 'metrics';
  readonly stt_ms: number | null;
  readonly first_token_ms: number | null;
  readonly first_audio_ms: number | null;
  readonly total_ms: number;
  readonly tools: readonly string[];
}

export interface SpeakerRejectedMessage {
  readonly type: 'speaker_rejected';
  readonly score: number;
}

export type EnrollmentStatus = 'recording' | 'complete' | 'cancelled' | 'failed';

export interface EnrollmentMessage {
  readonly type: 'enrollment';
  readonly status: EnrollmentStatus;
  readonly collected: number;
  readonly required: number;
}

/** A proactive message, e.g. a reminder that just fired. */
export interface NotificationMessage {
  readonly type: 'notification';
  readonly kind: string;
  readonly text: string;
}

/** Server data changed; widgets showing `topic` should refetch. */
export interface DataChangedMessage {
  readonly type: 'data_changed';
  readonly topic: string;
}

export interface ErrorMessage {
  readonly type: 'error';
  readonly message: string;
}

export type ServerMessage =
  | ReadyMessage
  | StateMessage
  | WakeMessage
  | InterruptedMessage
  | TranscriptMessage
  | AssistantDeltaMessage
  | ToolMessage
  | SpeechSegmentMessage
  | TurnCompleteMessage
  | MetricsMessage
  | SpeakerRejectedMessage
  | EnrollmentMessage
  | NotificationMessage
  | DataChangedMessage
  | ErrorMessage;

// ------------------------------------------------------------ client → server

export type ClientMessage =
  | { readonly type: 'activate' }
  | { readonly type: 'listen' }
  | { readonly type: 'text_query'; readonly text: string }
  | { readonly type: 'playback_ended'; readonly segment_id: string }
  | { readonly type: 'cancel' }
  | { readonly type: 'barge_in' }
  | { readonly type: 'enroll_voice' };

const SERVER_MESSAGE_TYPES = new Set<ServerMessage['type']>([
  'ready',
  'state',
  'wake',
  'interrupted',
  'transcript',
  'assistant_delta',
  'tool',
  'speech_segment',
  'turn_complete',
  'metrics',
  'speaker_rejected',
  'enrollment',
  'notification',
  'data_changed',
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
