/**
 * Observable assistant state (Zustand vanilla store).
 *
 * The store is framework-agnostic so the {@link VoiceAssistant} controller
 * can write to it; React components subscribe via `useAssistant`.
 *
 * @module
 */
import { createStore } from 'zustand/vanilla';

import type {
  AssistantState,
  EnrollmentStatus,
  MetricsMessage,
  ReadyMessage,
} from '../core/voice/protocol';
import {
  type ConversationEntry,
  type Speaker,
  addEntry,
  addNotice,
  appendAssistantDelta,
  completeAssistantTurn,
} from './conversation';

/** Link status to the core service. */
export type ConnectionStatus = 'connecting' | 'online' | 'offline';

/** Voice-ID enrollment progress shown in the enrollment overlay. */
export interface EnrollmentView {
  readonly status: EnrollmentStatus;
  readonly collected: number;
  readonly required: number;
}

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
  readonly soundsEnabled: boolean;
  readonly entries: readonly ConversationEntry[];
  /** Label of the tool running right now ("Checking the weather"). */
  readonly activeTool: string | null;
  readonly lastMetrics: MetricsMessage | null;
  readonly enrollment: EnrollmentView | null;
  /** Bumped when the server reports `data_changed` for a topic. */
  readonly dataVersions: Readonly<Record<string, number>>;
  /** Epoch ms of the last rejected (unrecognised) voice. */
  readonly rejectedAt: number | null;
}

/** State transitions. Only the controller should call these. */
export interface AssistantActions {
  setConnection(connection: ConnectionStatus): void;
  setState(state: AssistantState): void;
  setCapabilities(capabilities: ReadyMessage): void;
  setEngaged(engaged: boolean): void;
  setMic(active: boolean, error?: string | null): void;
  setSoundsEnabled(enabled: boolean): void;
  addMessage(speaker: Speaker, text: string, isError?: boolean): void;
  /** A proactive announcement from the core (`kind`: reminder, timer, alert, briefing…). */
  addNotice(kind: string, text: string): void;
  appendAssistant(delta: string): void;
  completeAssistant(text: string): void;
  setActiveTool(label: string | null): void;
  setMetrics(metrics: MetricsMessage): void;
  setEnrollment(enrollment: EnrollmentView | null): void;
  bumpData(topic: string): void;
  markRejected(): void;
}

export type AssistantStore = AssistantSnapshot & AssistantActions;

const SOUNDS_KEY = 'jarvis.sounds';

function loadSoundsPreference(): boolean {
  try {
    return globalThis.localStorage?.getItem(SOUNDS_KEY) !== 'off';
  } catch {
    return true;
  }
}

/** Create a fresh store (one per {@link VoiceAssistant}). */
export function createAssistantStore() {
  return createStore<AssistantStore>()((set) => ({
    connection: 'connecting',
    state: 'idle',
    capabilities: null,
    engaged: false,
    micActive: false,
    micError: null,
    soundsEnabled: loadSoundsPreference(),
    entries: [],
    activeTool: null,
    lastMetrics: null,
    enrollment: null,
    dataVersions: {},
    rejectedAt: null,

    setConnection: (connection) =>
      set((s) => ({ connection, state: connection === 'online' ? s.state : 'idle' })),
    setState: (state) =>
      set((s) => ({ state, activeTool: state === 'thinking' ? s.activeTool : null })),
    setCapabilities: (capabilities) => set({ capabilities }),
    setEngaged: (engaged) => set({ engaged }),
    setMic: (micActive, micError = null) => set({ micActive, micError }),
    setSoundsEnabled: (soundsEnabled) => {
      try {
        globalThis.localStorage?.setItem(SOUNDS_KEY, soundsEnabled ? 'on' : 'off');
      } catch {
        // Storage may be unavailable (private mode); the setting is then per-session.
      }
      set({ soundsEnabled });
    },
    addMessage: (speaker, text, isError = false) =>
      set((s) => ({ entries: addEntry(s.entries, speaker, text, isError) })),
    addNotice: (kind, text) => set((s) => ({ entries: addNotice(s.entries, kind, text) })),
    appendAssistant: (delta) => set((s) => ({ entries: appendAssistantDelta(s.entries, delta) })),
    completeAssistant: (text) => set((s) => ({ entries: completeAssistantTurn(s.entries, text) })),
    setActiveTool: (activeTool) => set({ activeTool }),
    setMetrics: (lastMetrics) => set({ lastMetrics }),
    setEnrollment: (enrollment) => set({ enrollment }),
    bumpData: (topic) =>
      set((s) => ({
        dataVersions: { ...s.dataVersions, [topic]: (s.dataVersions[topic] ?? 0) + 1 },
      })),
    markRejected: () => set({ rejectedAt: Date.now() }),
  }));
}

export type AssistantStoreApi = ReturnType<typeof createAssistantStore>;
