/**
 * Typed REST client for the core service's data endpoints.
 *
 * @module
 */
import { CORE_HTTP_URL } from '../../config';
import { authHeaders, markUnpaired } from './session';

/** A to-do item (`GET /api/tasks`). */
export interface Task {
  readonly id: number;
  readonly title: string;
  readonly done: boolean;
  readonly created_at: string;
  readonly completed_at: string | null;
}

/** An upcoming reminder (`GET /api/reminders`). */
export interface Reminder {
  readonly id: number;
  readonly text: string;
  readonly due_at: string;
  readonly created_at: string;
}

/** A running countdown (`GET /api/timers`); the UI counts down to `ends_at`. */
export interface Timer {
  readonly id: number;
  /** What it's for, e.g. "rice" ("" if unnamed). */
  readonly label: string;
  readonly duration_s: number;
  readonly ends_at: string;
  readonly created_at: string;
}

/** Something Jarvis announced (`GET /api/notifications`). */
export interface NotificationItem {
  readonly id: number;
  /** `reminder`, `timer`, `alert`, `briefing`… */
  readonly kind: string;
  readonly text: string;
  readonly created_at: string;
  readonly read: boolean;
}

/** The notifications center: newest first, plus the unread count. */
export interface NotificationsResponse {
  readonly unread: number;
  readonly items: readonly NotificationItem[];
}

/** A long-term memory (`GET /api/memories`). */
export interface Memory {
  readonly id: number;
  readonly text: string;
  readonly created_at: string;
}

/** Everything editable in the Settings screen (mirrors `RuntimeSettings`). */
export interface RuntimeSettings {
  readonly user_name: string;
  readonly persona_formality: 'formal' | 'balanced' | 'casual';
  readonly persona_verbosity: 'brief' | 'balanced' | 'detailed';
  readonly persona_humour: 'none' | 'dry' | 'playful';
  readonly tts_voice: string;
  readonly tts_speed: number;
  readonly wake_threshold: number;
  readonly end_of_speech_ms: number;
  readonly listen_timeout_ms: number;
  readonly follow_up_ms: number;
  readonly barge_in: 'off' | 'wake_word' | 'voice';
  readonly barge_in_min_speech_ms: number;
  readonly speaker_threshold: number;
  readonly llm_model: string;
  readonly default_location: string;
  readonly briefing_time: string;
  readonly news_feeds: readonly string[];
  readonly calendar_urls: readonly string[];
  /** PisoTiyempo desktop feed address ("" = read its export files only). */
  readonly portfolio_feed_url: string;
}

export interface SettingsResponse {
  readonly values: RuntimeSettings;
  readonly defaults: RuntimeSettings;
}

export interface VoiceOption {
  readonly id: string;
  readonly label: string;
}

export interface ModelsResponse {
  readonly current: string;
  readonly available: readonly string[];
}

export interface Weather {
  readonly location: string;
  readonly temperature_c: number;
  readonly feels_like_c: number;
  readonly description: string;
  readonly wind_kph: number;
  readonly humidity_pct: number;
  readonly high_c: number | null;
  readonly low_c: number | null;
}

export interface Headline {
  readonly title: string;
  readonly source: string;
  readonly url: string;
  readonly published: string | null;
}

export interface CalendarEvent {
  readonly title: string;
  readonly start: string;
  readonly end: string;
  readonly all_day: boolean;
  readonly location: string;
  readonly calendar: string;
}

export interface CalendarResponse {
  readonly configured: boolean;
  readonly events: readonly CalendarEvent[];
}

export interface GpuSnapshot {
  readonly name: string;
  readonly utilization_pct: number;
  readonly memory_used_mb: number;
  readonly memory_total_mb: number;
  readonly temperature_c: number | null;
}

export interface SystemSnapshot {
  readonly cpu_percent: number;
  readonly memory_used_gb: number;
  readonly memory_total_gb: number;
  readonly gpus: readonly GpuSnapshot[];
  readonly uptime_s: number;
}

/** Portfolio totals in pesos; percentages are in percent (1.5 = +1.5 %). */
export interface PortfolioTotals {
  readonly market_value: number;
  readonly cost_basis: number;
  readonly day_change: number;
  readonly day_change_pct: number | null;
  readonly unrealized_pnl: number;
  readonly unrealized_pct: number;
}

/** One position and its move on the latest trading day. */
export interface PortfolioHolding {
  readonly symbol: string;
  readonly sector: string;
  readonly shares: number;
  readonly last_price: number | null;
  readonly change_pct: number | null;
  readonly day_change: number;
  readonly market_value: number;
  readonly unrealized_pnl: number;
  readonly unrealized_pct: number;
}

/** A PSE stock that passed the trend-and-value screen. */
export interface StockIdea {
  readonly symbol: string;
  readonly name: string;
  readonly sector: string;
  readonly close: number;
  readonly change_pct: number | null;
  readonly score: number;
  readonly rsi14: number | null;
  readonly return_3m_pct: number | null;
  readonly reasons: readonly string[];
}

/** One of your PisoTiyempo alerts that holds at the latest close. */
export interface StockAlert {
  readonly symbol: string;
  /** `PRICE_ABOVE`, `PRICE_BELOW`, `BUY_SIGNAL`, `SELL_SIGNAL` or `PATTERN`. */
  readonly kind: string;
  readonly message: string;
  readonly date: string;
}

/** `GET /api/apps/pisotiyempo`: the Portfolio widget's data. */
export interface PisoTiyempoResponse {
  readonly status: 'ok' | 'unavailable' | 'disabled';
  readonly message: string;
  readonly source: string;
  /** Trading date of the prices (YYYY-MM-DD). */
  readonly session_date: string | null;
  /** Whether that date is today in Philippine time. */
  readonly is_today: boolean;
  readonly totals: PortfolioTotals | null;
  readonly holdings: readonly PortfolioHolding[];
  readonly ideas: readonly StockIdea[];
  /** Your alerts that triggered at the latest close. */
  readonly alerts: readonly StockAlert[];
  /** The screen's rules in one sentence. */
  readonly screen: string;
  readonly disclaimer: string;
}

/** `GET /api/session`: whether this is the PC itself or a paired device. */
export interface SessionInfo {
  readonly local: boolean;
  readonly device: string | null;
}

/** A device paired for phone access (tokens are never shown again). */
export interface Device {
  readonly id: number;
  readonly name: string;
  readonly created_at: string;
  readonly last_used_at: string | null;
}

/** A newly paired device: `pair_url` opens Jarvis on the phone and pairs it. */
export interface PairedDevice extends Device {
  readonly token: string;
  /** Empty until `tailscale serve` publishes Jarvis. */
  readonly pair_url: string;
}

/** `GET /api/devices/remote`: what the Phone access setup still needs. */
export interface RemoteStatus {
  readonly installed: boolean;
  readonly running: boolean;
  readonly dns_name: string;
  readonly public_url: string;
  readonly port: number;
  /** Whether the core serves the built dashboard (needed for phones). */
  readonly web_ui: boolean;
}

/** Raised for non-2xx responses; `message` carries the server's explanation. */
export class ApiError extends Error {
  override readonly name = 'ApiError';
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${CORE_HTTP_URL}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...authHeaders(), ...init?.headers },
  });
  if (response.status === 401) markUnpaired(); // a phone whose token is missing or revoked
  if (!response.ok) {
    let detail = `${init?.method ?? 'GET'} ${path} → ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === 'string') detail = body.detail;
    } catch {
      // Non-JSON error body: keep the generic message.
    }
    throw new ApiError(response.status, detail);
  }
  return (response.status === 204 ? undefined : await response.json()) as T;
}

const put = (body: unknown): RequestInit => ({ method: 'PUT', body: JSON.stringify(body) });

/** Data API of the core service. */
export const coreApi = {
  listTasks: () => request<Task[]>('/api/tasks'),
  createTask: (title: string) =>
    request<Task>('/api/tasks', { method: 'POST', body: JSON.stringify({ title }) }),
  setTaskDone: (id: number, done: boolean) =>
    request<Task>(`/api/tasks/${id}`, { method: 'PATCH', body: JSON.stringify({ done }) }),
  deleteTask: (id: number) => request<undefined>(`/api/tasks/${id}`, { method: 'DELETE' }),
  listReminders: () => request<Reminder[]>('/api/reminders'),
  deleteReminder: (id: number) => request<undefined>(`/api/reminders/${id}`, { method: 'DELETE' }),
  listTimers: () => request<Timer[]>('/api/timers'),
  /** Start a timer from text like "10 min" or "12 min tea" (the rest becomes the label). */
  startTimer: (duration: string, label = '') =>
    request<Timer>('/api/timers', { method: 'POST', body: JSON.stringify({ duration, label }) }),
  cancelTimer: (id: number) => request<undefined>(`/api/timers/${id}`, { method: 'DELETE' }),
  listNotifications: (limit = 50) =>
    request<NotificationsResponse>(`/api/notifications?limit=${limit}`),
  /** Mark `ids` (or, without them, everything) as read. */
  markNotificationsRead: (ids?: readonly number[]) =>
    request<NotificationsResponse>('/api/notifications/read', {
      method: 'POST',
      body: JSON.stringify(ids ? { ids } : {}),
    }),
  clearNotifications: () => request<undefined>('/api/notifications', { method: 'DELETE' }),
  listMemories: () => request<Memory[]>('/api/memories'),
  deleteMemory: (id: number) => request<undefined>(`/api/memories/${id}`, { method: 'DELETE' }),
  resetVoiceprint: () => request<undefined>('/api/voiceprint', { method: 'DELETE' }),

  getSettings: () => request<SettingsResponse>('/api/settings'),
  updateSettings: (patch: Partial<RuntimeSettings>) =>
    request<SettingsResponse>('/api/settings', put(patch)),
  resetSettings: () => request<SettingsResponse>('/api/settings/reset', { method: 'POST' }),
  listVoices: () => request<VoiceOption[]>('/api/voices'),
  listModels: () => request<ModelsResponse>('/api/models'),

  getUiPreference: <T>(key: string) => request<T | null>(`/api/ui-preferences/${key}`),
  putUiPreference: (key: string, value: unknown) =>
    request<undefined>(`/api/ui-preferences/${key}`, put(value)),

  getWeather: (location = '') =>
    request<Weather | null>(`/api/weather?location=${encodeURIComponent(location)}`),
  getNews: (limit = 8) => request<Headline[]>(`/api/news?limit=${limit}`),
  getCalendar: (days = 2) => request<CalendarResponse>(`/api/calendar?days=${days}`),
  getSystem: () => request<SystemSnapshot>('/api/system'),
  getPisoTiyempo: () => request<PisoTiyempoResponse>('/api/apps/pisotiyempo'),

  getSession: () => request<SessionInfo>('/api/session'),
  listDevices: () => request<Device[]>('/api/devices'),
  pairDevice: (name: string) =>
    request<PairedDevice>('/api/devices', { method: 'POST', body: JSON.stringify({ name }) }),
  revokeDevice: (id: number) => request<undefined>(`/api/devices/${id}`, { method: 'DELETE' }),
  getRemoteStatus: () => request<RemoteStatus>('/api/devices/remote'),
};

/**
 * Phrase a reminder time relative to now: "in 12 min", "today 3:05 PM",
 * "tomorrow 9:00 AM", "Fri 14 Nov 6:30 PM".
 */
export function relativeTime(iso: string, now: Date = new Date()): string {
  const when = new Date(iso);
  const minutes = Math.round((when.getTime() - now.getTime()) / 60_000);
  if (minutes < 1) return 'now';
  if (minutes < 60) return `in ${minutes} min`;
  const clock = when.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
  const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const days = Math.round((startOfDay(when) - startOfDay(now)) / 86_400_000);
  if (days === 0) return `today ${clock}`;
  if (days === 1) return `tomorrow ${clock}`;
  const date = when.toLocaleDateString(undefined, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  });
  return `${date} ${clock}`;
}
