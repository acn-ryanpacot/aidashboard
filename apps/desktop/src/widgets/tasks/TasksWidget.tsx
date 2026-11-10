import { Bell, Check, Plus, X } from 'lucide-react';
import { type FormEvent, useState } from 'react';

import { coreApi, relativeTime } from '../../core/api/client';
import { useCoreData } from '../../core/api/useCoreData';
import { cn } from '../../lib/cn';

/**
 * Open tasks and upcoming reminders, stored by the core service.
 *
 * Changes made by voice ("add milk to my list") or by any other client
 * arrive as `data_changed` events and refresh this widget automatically.
 */
export function TasksWidget() {
  const tasks = useCoreData(['tasks'], coreApi.listTasks);
  const reminders = useCoreData(['reminders'], coreApi.listReminders);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState<number | null>(null);

  const add = async (event: FormEvent) => {
    event.preventDefault();
    const title = draft.trim();
    if (!title) return;
    setDraft('');
    await coreApi.createTask(title).catch(() => setDraft(title));
    tasks.reload();
  };

  const complete = async (id: number) => {
    setBusy(id);
    try {
      await coreApi.setTaskDone(id, true);
    } finally {
      setBusy(null);
      tasks.reload();
    }
  };

  const cancelReminder = async (id: number) => {
    await coreApi.deleteReminder(id).catch(() => undefined);
    reminders.reload();
  };

  const openTasks = tasks.data ?? [];
  const upcoming = (reminders.data ?? []).slice(0, 3);

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <form onSubmit={(e) => void add(e)} className="flex items-center gap-2">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Add a task…"
          aria-label="New task"
          className="h-8 flex-1 rounded-lg border border-white/8 bg-white/[0.03] px-3 text-[13px] text-white/85 placeholder:text-white/25 focus:border-arc-400/40 focus:outline-none"
        />
        <button
          type="submit"
          disabled={!draft.trim()}
          aria-label="Add task"
          className="flex size-8 items-center justify-center rounded-lg bg-white/5 text-white/60 transition hover:bg-white/10 disabled:opacity-30"
        >
          <Plus className="size-4" />
        </button>
      </form>

      <ul className="hud-scroll -mr-2 min-h-0 flex-1 space-y-1 overflow-y-auto pr-2">
        {tasks.error && <li className="text-xs text-signal-red/70">Couldn't load tasks.</li>}
        {!tasks.error && openTasks.length === 0 && (
          <li className="py-2 text-[13px] text-white/30">
            Nothing pending. Try “Jarvis, add buy milk to my tasks”.
          </li>
        )}
        {openTasks.map((task) => (
          <li key={task.id} className="group flex items-center gap-3 py-1">
            <button
              type="button"
              onClick={() => void complete(task.id)}
              disabled={busy === task.id}
              aria-label={`Complete ${task.title}`}
              className={cn(
                'flex size-4 shrink-0 items-center justify-center rounded-[5px] border transition',
                'border-white/20 text-transparent hover:border-arc-400/70 hover:text-arc-300',
              )}
            >
              <Check className="size-3" strokeWidth={3} />
            </button>
            <span className="truncate text-[13.5px] text-white/80">{task.title}</span>
          </li>
        ))}
      </ul>

      {upcoming.length > 0 && (
        <div className="space-y-1.5 border-t border-white/5 pt-3">
          {upcoming.map((reminder) => (
            <div key={reminder.id} className="group flex items-center gap-2.5 text-[12.5px]">
              <Bell className="size-3.5 shrink-0 text-gold-400/70" />
              <span className="truncate text-white/70">{reminder.text}</span>
              <span className="ml-auto shrink-0 font-mono text-[10px] text-white/35">
                {relativeTime(reminder.due_at)}
              </span>
              <button
                type="button"
                onClick={() => void cancelReminder(reminder.id)}
                aria-label={`Cancel reminder ${reminder.text}`}
                className="text-white/0 transition group-hover:text-white/40 hover:text-white/70"
              >
                <X className="size-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
