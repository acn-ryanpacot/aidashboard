/**
 * Formatting for the Money widget: amounts in the sheet's currency, due-date
 * labels and their urgency.
 *
 * @module
 */

const formats = new Map<string, Intl.NumberFormat>();

/** "₱182,400", "₱3,210.50", "$12" (centavos only when there are any). */
export function formatMoney(amount: number, currency = '₱'): string {
  const cents = Math.round(amount * 100) % 100 !== 0;
  const key = String(cents);
  let format = formats.get(key);
  if (!format) {
    format = new Intl.NumberFormat('en-PH', {
      minimumFractionDigits: cents ? 2 : 0,
      maximumFractionDigits: 2,
    });
    formats.set(key, format);
  }
  const sign = amount < 0 ? '−' : '';
  return `${sign}${currency}${format.format(Math.abs(amount))}`;
}

/** What hidden amounts show instead (screen sharing, people looking over). */
export const HIDDEN_AMOUNT = '•••••';

/** "today", "tomorrow", "in 4 days", "2 days late". */
export function dueLabel(days: number): string {
  if (days < 0) return days === -1 ? '1 day late' : `${-days} days late`;
  if (days === 0) return 'today';
  if (days === 1) return 'tomorrow';
  return `in ${days} days`;
}

/** How urgent a payment looks: overdue, inside the reminder window, or later. */
export type DueTone = 'overdue' | 'soon' | 'later';

export function dueTone(days: number, reminderDays: number): DueTone {
  if (days < 0) return 'overdue';
  return days <= Math.max(reminderDays, 1) ? 'soon' : 'later';
}

/** "Wed 18 Nov" from `YYYY-MM-DD` (read as a local date, not UTC). */
export function formatDueDate(iso: string): string {
  const [year, month, day] = iso.split('-').map(Number);
  const when = new Date(year ?? 1970, (month ?? 1) - 1, day ?? 1);
  return when.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' });
}

/** Total of the payments due within `days` (overdue ones included). */
export function dueTotal(
  payments: readonly { readonly days: number; readonly amount: number | null }[],
  days: number,
): number {
  return payments.filter((p) => p.days <= days).reduce((sum, p) => sum + (p.amount ?? 0), 0);
}
