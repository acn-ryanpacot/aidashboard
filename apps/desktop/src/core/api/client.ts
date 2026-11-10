/**
 * Typed REST client for the core service's data endpoints.
 *
 * @module
 */
import { CORE_HTTP_URL } from '../../config';

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
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  });
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
