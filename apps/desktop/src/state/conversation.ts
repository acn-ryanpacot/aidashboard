/**
 * Pure reducers for the conversation transcript shown in the HUD.
 *
 * @module
 */

/** Who wrote a transcript entry. */
export type Speaker = 'user' | 'assistant' | 'system';

/** One line of the visible conversation. */
export interface ConversationEntry {
  readonly id: string;
  readonly speaker: Speaker;
  readonly text: string;
  /** `true` while the assistant is still streaming this entry. */
  readonly streaming: boolean;
  /** Marks system entries that report a failure. */
  readonly isError?: boolean;
  /** Creation time (epoch ms). */
  readonly at: number;
}

/** Entries kept in memory; older ones scroll away. */
export const MAX_ENTRIES = 60;

let counter = 0;
const nextId = () => `entry-${Date.now().toString(36)}-${(counter++).toString(36)}`;

function push(entries: readonly ConversationEntry[], entry: Omit<ConversationEntry, 'id' | 'at'>) {
  const next = [...entries, { ...entry, id: nextId(), at: Date.now() }];
  return next.length > MAX_ENTRIES ? next.slice(next.length - MAX_ENTRIES) : next;
}

function lastIfStreaming(entries: readonly ConversationEntry[]): ConversationEntry | undefined {
  const last = entries.at(-1);
  return last?.speaker === 'assistant' && last.streaming ? last : undefined;
}

/** Add a finished message from `speaker`. */
export function addEntry(
  entries: readonly ConversationEntry[],
  speaker: Speaker,
  text: string,
  isError = false,
): ConversationEntry[] {
  return push(entries, { speaker, text, streaming: false, isError });
}

/** Append a streamed delta to the assistant's in-progress answer (creating it if needed). */
export function appendAssistantDelta(
  entries: readonly ConversationEntry[],
  delta: string,
): ConversationEntry[] {
  const current = lastIfStreaming(entries);
  if (!current) return push(entries, { speaker: 'assistant', text: delta, streaming: true });
  return [...entries.slice(0, -1), { ...current, text: current.text + delta }];
}

/** Finalise the assistant's answer with the authoritative full text. */
export function completeAssistantTurn(
  entries: readonly ConversationEntry[],
  text: string,
): ConversationEntry[] {
  const current = lastIfStreaming(entries);
  if (!current) return addEntry(entries, 'assistant', text);
  return [...entries.slice(0, -1), { ...current, text, streaming: false }];
}
