/**
 * Load data from the core service and refetch whenever the server announces
 * a change (`data_changed`) or the link comes back online.
 *
 * @module
 */
import { useCallback, useEffect, useState } from 'react';

import { useAssistant } from '../voice/hooks';

/** Result of {@link useCoreData}. */
export interface CoreData<T> {
  readonly data: T | null;
  readonly error: string | null;
  /** Fetch again now (e.g. after an optimistic update). */
  readonly reload: () => void;
}

/**
 * @param topics - `data_changed` topics that invalidate this data.
 * @param load - Fetcher; keep it referentially stable (module-level or `useCallback`).
 *
 * @example
 * ```tsx
 * const { data: tasks } = useCoreData(['tasks'], coreApi.listTasks);
 * ```
 */
export function useCoreData<T>(topics: readonly string[], load: () => Promise<T>): CoreData<T> {
  const online = useAssistant((s) => s.connection === 'online');
  const version = useAssistant((s) => topics.reduce((sum, t) => sum + (s.dataVersions[t] ?? 0), 0));
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const reload = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    if (!online) return;
    let cancelled = false;
    load()
      .then((result) => {
        if (cancelled) return;
        setData(result);
        setError(null);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason));
      });
    return () => {
      cancelled = true;
    };
  }, [online, version, nonce, load]);

  return { data, error, reload };
}
