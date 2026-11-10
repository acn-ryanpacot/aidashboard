/**
 * Push-to-talk: start listening without the wake word or greeting.
 *
 * - In the window: **Ctrl/⌘ + Space**.
 * - System-wide (Tauri only): **Ctrl + Shift + Space**, registered by the
 *   Rust shell, which emits a `push-to-talk` event to the web view.
 *
 * @module
 */
import { useEffect } from 'react';

import { useVoiceAssistant } from './hooks';

/** Name of the Tauri event emitted by the global shortcut. */
export const PUSH_TO_TALK_EVENT = 'push-to-talk';

/** Whether the app runs inside the Tauri shell (vs. a plain browser). */
export function isTauri(): boolean {
  return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;
}

/** Whether a key event is the in-window push-to-talk chord. */
export function isPushToTalkChord(
  event: Pick<KeyboardEvent, 'code' | 'ctrlKey' | 'metaKey' | 'repeat'>,
): boolean {
  return event.code === 'Space' && (event.ctrlKey || event.metaKey) && !event.repeat;
}

/** Wire up push-to-talk for the lifetime of the calling component. */
export function usePushToTalk(): void {
  const assistant = useVoiceAssistant();

  useEffect(() => {
    const trigger = () => {
      if (assistant.store.getState().engaged) assistant.listen();
    };
    const onKey = (event: KeyboardEvent) => {
      if (!isPushToTalkChord(event)) return;
      event.preventDefault();
      trigger();
    };
    window.addEventListener('keydown', onKey);

    let unlisten: (() => void) | undefined;
    let disposed = false;
    if (isTauri()) {
      void import('@tauri-apps/api/event')
        .then(({ listen }) => listen(PUSH_TO_TALK_EVENT, trigger))
        .then((stop) => {
          if (disposed) stop();
          else unlisten = stop;
        })
        .catch((error: unknown) => console.warn('Global push-to-talk unavailable', error));
    }

    return () => {
      disposed = true;
      window.removeEventListener('keydown', onKey);
      unlisten?.();
    };
  }, [assistant]);
}
