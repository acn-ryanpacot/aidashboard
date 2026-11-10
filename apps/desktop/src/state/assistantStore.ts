/**
 * Observable assistant state (Zustand vanilla store).
 *
 * The store is framework-agnostic so the {@link VoiceAssistant} controller
 * can write to it; React components subscribe via `useAssistant`.
 *
 * @module
 */
import { createStore } from 'zustand/vanilla';

import type { AssistantState, ReadyMessage } from '../core/voice/protocol';
import {
  type ConversationEntry,
  type Speaker,
  addEntry,
  appendAssistantDelta,
  completeAssistantTurn,
} from './conversation';

/** Link status to the core service. */
export type ConnectionStatus = 'connecting' | 'online' | 'offline';

/** Everything the UI renders about the assistant. */
export interface AssistantSnapshot {
  readonly connection: ConnectionStatus;
  readonly state: AssistantState;
  /** Server capabilities, received on connect. */
  readonly capabilities: ReadyMessage | null;
  /** The user has clicked "Engage" (audio unlocked). */
  readonly engaged: boolean;
  readonly micActive: boolean;
  readonly micError: string | null;
  readonly entries: readonly ConversationEntry[];
}

/** State transitions. Only the controller should call these. */
export interface AssistantActions {
  setConnection(connection: ConnectionStatus): void;
  setState(state: AssistantState): void;
  setCapabilities(capabilities: ReadyMessage): void;
  setEngaged(engaged: boolean): void;
  setMic(active: boolean, error?: string | null): void;
  addMessage(speaker: Speaker, text: string, isError?: boolean): void;
  appendAssistant(delta: string): void;
  completeAssistant(text: string): void;
}

export type AssistantStore = AssistantSnapshot & AssistantActions;

/** Create a fresh store (one per {@link VoiceAssistant}). */
export function createAssistantStore() {
  return createStore<AssistantStore>()((set) => ({
    connection: 'connecting',
    state: 'idle',
    capabilities: null,
    engaged: false,
    micActive: false,
    micError: null,
    entries: [],

    setConnection: (connection) =>
      set((s) => ({ connection, state: connection === 'online' ? s.state : 'idle' })),
    setState: (state) => set({ state }),
    setCapabilities: (capabilities) => set({ capabilities }),
    setEngaged: (engaged) => set({ engaged }),
    setMic: (micActive, micError = null) => set({ micActive, micError }),
    addMessage: (speaker, text, isError = false) =>
      set((s) => ({ entries: addEntry(s.entries, speaker, text, isError) })),
    appendAssistant: (delta) => set((s) => ({ entries: appendAssistantDelta(s.entries, delta) })),
    completeAssistant: (text) => set((s) => ({ entries: completeAssistantTurn(s.entries, text) })),
  }));
}

export type AssistantStoreApi = ReturnType<typeof createAssistantStore>;
