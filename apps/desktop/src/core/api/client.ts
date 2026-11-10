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

/** Raised for non-2xx responses. */
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
    throw new ApiError(response.status, `${init?.method ?? 'GET'} ${path} → ${response.status}`);
  }
  return (response.status === 204 ? undefined : await response.json()) as T;
}

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
