/**
 * Display formatting helpers.
 *
 * @module
 */

/** Format milliseconds as "0.84 s" / "320 ms"; "—" when unknown. */
export function formatLatency(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '—';
  return ms >= 1000 ? `${(ms / 1000).toFixed(2)} s` : `${Math.round(ms)} ms`;
}
