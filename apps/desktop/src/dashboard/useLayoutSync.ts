import { useEffect } from 'react';

import { coreApi } from '../core/api/client';
import { useAssistant } from '../core/voice/hooks';
import { useLayout } from './layoutStore';

/**
 * Load the saved layout from the core service whenever the link comes up,
 * and again when another client changes it.
 */
export function useLayoutSync(): void {
  const online = useAssistant((s) => s.connection === 'online');
  const version = useAssistant((s) => s.dataVersions['ui:layout'] ?? 0);
  const hydrate = useLayout((s) => s.hydrate);

  useEffect(() => {
    if (!online) return;
    let cancelled = false;
    coreApi
      .getUiPreference<unknown>('layout')
      .then((value) => {
        if (!cancelled) hydrate(value);
      })
      .catch((error: unknown) => console.warn('Could not load the saved layout', error));
    return () => {
      cancelled = true;
    };
  }, [online, version, hydrate]);
}
