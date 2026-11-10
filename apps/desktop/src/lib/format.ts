/**
 * Display formatting helpers.
 *
 * @module
 */
import type { CalendarEvent } from '../core/api/client';

/** Format milliseconds as "0.84 s" / "320 ms"; "—" when unknown. */
export function formatLatency(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '—';
  return ms >= 1000 ? `${(ms / 1000).toFixed(2)} s` : `${Math.round(ms)} ms`;
}

/** "2h", "35m" — compact age of a headline. */
export function headlineAge(published: string | null, now: Date = new Date()): string {
  if (!published) return '';
  const minutes = Math.max(0, Math.round((now.getTime() - new Date(published).getTime()) / 60_000));
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.round(minutes / 60);
  return hours < 48 ? `${hours}h` : `${Math.round(hours / 24)}d`;
}

/** Group events under "Today" / "Tomorrow". */
export function groupByDay(
  events: readonly CalendarEvent[],
  now: Date = new Date(),
): { label: string; events: CalendarEvent[] }[] {
  const dayKey = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const today = dayKey(now);
  const groups = new Map<string, CalendarEvent[]>();
  for (const event of events) {
    const offset = Math.round((dayKey(new Date(event.start)) - today) / 86_400_000);
    const label = offset <= 0 ? 'Today' : offset === 1 ? 'Tomorrow' : 'Later';
    groups.set(label, [...(groups.get(label) ?? []), event]);
  }
  return [...groups].map(([label, list]) => ({ label, events: list }));
}

/** "3d 4h", "5h 12m", "18m". */
export function formatUptime(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);
  if (days > 0) return `${days}d ${hours % 24}h`;
  if (hours > 0) return `${hours}h ${minutes % 60}m`;
  return `${minutes}m`;
}
