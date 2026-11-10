import { useEffect } from 'react';

import { useAssistant } from '../../core/voice/hooks';
import { useUi } from '../../state/uiStore';

const ACTIVITY_EVENTS = ['pointermove', 'pointerdown', 'keydown', 'wheel', 'touchstart'] as const;

/**
 * Enter ambient mode after `ambientAfterMin` minutes without input while
 * Jarvis is idle and nothing modal is open; any activity leaves it.
 */
export function useAmbientMode(): void {
  const minutes = useUi((s) => s.ambientAfterMin);
  const ambient = useUi((s) => s.ambient);
  const setAmbient = useUi((s) => s.setAmbient);
  const state = useAssistant((s) => s.state);
  const engaged = useAssistant((s) => s.engaged);

  useEffect(() => {
    if (state !== 'idle' && ambient) setAmbient(false); // Jarvis woke up: show the HUD
  }, [state, ambient, setAmbient]);

  useEffect(() => {
    if (!engaged || minutes <= 0) return;
    let timer: ReturnType<typeof setTimeout>;
    const arm = () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        const ui = useUi.getState();
        if (ui.overlay === 'none' && !ui.editing) ui.setAmbient(true);
      }, minutes * 60_000);
    };
    const onActivity = () => {
      if (useUi.getState().ambient) useUi.getState().setAmbient(false);
      arm();
    };
    ACTIVITY_EVENTS.forEach((name) => window.addEventListener(name, onActivity, { passive: true }));
    arm();
    return () => {
      clearTimeout(timer);
      ACTIVITY_EVENTS.forEach((name) => window.removeEventListener(name, onActivity));
    };
  }, [engaged, minutes]);
}
