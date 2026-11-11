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

const pesoFormats = new Map<string, Intl.NumberFormat>();

/**
 * Philippine pesos: "₱101,500", or "+₱1,500" / "−₱203" with `signed`.
 * Prices under ₱1 keep four decimals (PSE penny stocks trade in ₱0.0001 ticks).
 */
export function formatPesos(
  amount: number,
  { signed = false, decimals }: { signed?: boolean; decimals?: number } = {},
): string {
  const digits = decimals ?? (Math.abs(amount) < 1 && amount !== 0 ? 4 : 0);
  const key = `${signed}:${digits}`;
  let format = pesoFormats.get(key);
  if (!format) {
    format = new Intl.NumberFormat('en-PH', {
      style: 'currency',
      currency: 'PHP',
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
      signDisplay: signed ? 'exceptZero' : 'auto',
    });
    pesoFormats.set(key, format);
  }
  return format.format(amount).replace('-', '−'); // a true minus sign, like formatPercent
}

/** "+1.50%", "−0.48%", "0.00%"; "—" when unknown. */
export function formatPercent(pct: number | null | undefined, decimals = 2): string {
  if (pct === null || pct === undefined || !Number.isFinite(pct)) return '—';
  const sign = pct > 0 ? '+' : pct < 0 ? '−' : '';
  return `${sign}${Math.abs(pct).toFixed(decimals)}%`;
}

/** Tailwind text colour for a gain, a loss or no change. */
export function moveColor(value: number | null | undefined): string {
  if (!value) return 'text-white/55';
  return value > 0 ? 'text-signal-green' : 'text-signal-red';
}

/**
 * "Today · Tue, Nov 10" or "Last session · Mon, Nov 9" for a trading date
 * (`YYYY-MM-DD`, read as a calendar date, not a UTC instant).
 */
export function formatSession(date: string | null, isToday: boolean): string {
  if (!date) return 'Last sync';
  return `${isToday ? 'Today' : 'Last session'} · ${formatTradingDate(date)}`;
}

/** "Tue, Nov 10" for a `YYYY-MM-DD` trading date ("" when unknown). */
export function formatTradingDate(date: string | null): string {
  if (!date) return '';
  const [year, month, day] = date.split('-').map(Number);
  return new Date(year ?? 1970, (month ?? 1) - 1, day ?? 1).toLocaleDateString(undefined, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  });
}

/**
 * A timer's remaining time: "9:42", "1:02:05"; with `words`, "10 min" / "1 h 30 min" / "45 s".
 */
export function formatCountdown(seconds: number, { words = false } = {}): string {
  const total = Math.max(0, Math.round(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (words) {
    const parts = [h && `${h} h`, m && `${m} min`, s && `${s} s`].filter(Boolean);
    return parts.join(' ') || '0 s';
  }
  const pad = (n: number) => String(n).padStart(2, '0');
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
}

/** How much of a timer has elapsed, 0 (just started) to 1 (done). */
export function timerProgress(
  timer: { readonly duration_s: number; readonly ends_at: string },
  now: number = Date.now(),
): number {
  if (timer.duration_s <= 0) return 1;
  const left = (new Date(timer.ends_at).getTime() - now) / 1000;
  return Math.min(1, Math.max(0, 1 - left / timer.duration_s));
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
