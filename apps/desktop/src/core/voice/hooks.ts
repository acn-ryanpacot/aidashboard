/**
 * React hooks for the voice assistant.
 *
 * @module
 */
import { useContext } from 'react';
import { useStore } from 'zustand';

import type { AssistantStore } from '../../state/assistantStore';
import { VoiceAssistantContext } from './context';
import type { VoiceAssistant } from './VoiceAssistant';

/** The app's voice assistant controller. */
export function useVoiceAssistant(): VoiceAssistant {
  const assistant = useContext(VoiceAssistantContext);
  if (!assistant) throw new Error('useVoiceAssistant must be used inside <VoiceAssistantProvider>');
  return assistant;
}

/**
 * Subscribe to a slice of assistant state; re-renders only when it changes.
 *
 * @example
 * ```tsx
 * const state = useAssistant((s) => s.state);
 * ```
 */
export function useAssistant<T>(selector: (store: AssistantStore) => T): T {
  return useStore(useVoiceAssistant().store, selector);
}
