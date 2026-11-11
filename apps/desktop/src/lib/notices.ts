/**
 * How announcements from the core are labelled, shared by the conversation
 * transcript and the notifications center.
 *
 * @module
 */

/** Label for an announcement, by the kind the core sent. */
const NOTICE_LABEL: Partial<Record<string, string>> = {
  reminder: 'Reminder',
  timer: 'Timer',
  alert: 'Stock alert',
  briefing: 'Briefing',
};

/** "Timer", "Stock alert"… ("Notice" for kinds this UI doesn't know yet). */
export const noticeLabel = (kind: string | undefined): string =>
  (kind && NOTICE_LABEL[kind]) ?? 'Notice';

/** A group of notifications under a day heading. */
export interface DayGroup<T> {
  readonly label: string;
  readonly items: T[];
}

/**
 * Group items (newest first) under "Today", "Yesterday" or a short date,
 * keeping their order.
 */
export function groupByDayLabel<T extends { readonly created_at: string }>(
  items: readonly T[],
  now: Date = new Date(),
): DayGroup<T>[] {
  const dayKey = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const today = dayKey(now);
  const groups: DayGroup<T>[] = [];
  for (const item of items) {
    const when = new Date(item.created_at);
    const offset = Math.round((today - dayKey(when)) / 86_400_000);
    const label =
      offset <= 0
        ? 'Today'
        : offset === 1
          ? 'Yesterday'
          : when.toLocaleDateString(undefined, {
              weekday: 'short',
              day: 'numeric',
              month: 'short',
            });
    const last = groups.at(-1);
    if (last?.label === label) last.items.push(item);
    else groups.push({ label, items: [item] });
  }
  return groups;
}
