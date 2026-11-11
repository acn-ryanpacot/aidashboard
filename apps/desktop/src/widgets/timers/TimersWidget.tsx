import { Play, X } from 'lucide-react';
import { type FormEvent, useEffect, useState } from 'react';

import { ApiError, type Timer, coreApi } from '../../core/api/client';
import { useCoreData } from '../../core/api/useCoreData';
import { cn } from '../../lib/cn';
import { formatCountdown, timerProgress } from '../../lib/format';

const PRESETS = ['1 min', '5 min', '10 min', '15 min'] as const;

/** Re-render on an interval while `active` (for live countdowns). */
function useNow(active: boolean, intervalMs = 250): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(timer);
  }, [active, intervalMs]);
  return now;
}

/** A thin circular progress ring that drains as the timer runs down. */
function Ring({ progress, done }: { progress: number; done: boolean }) {
  const radius = 15;
  const circumference = 2 * Math.PI * radius;
  return (
    <svg viewBox="0 0 36 36" className="size-9 shrink-0 -rotate-90" aria-hidden>
      <circle
        cx="18"
        cy="18"
        r={radius}
        fill="none"
        stroke="rgb(255 255 255 / 0.07)"
        strokeWidth="2.5"
      />
      <circle
        cx="18"
        cy="18"
        r={radius}
        fill="none"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={circumference * progress}
        className={cn(
          'transition-[stroke-dashoffset] duration-300 ease-linear',
          done ? 'text-gold-400' : 'text-arc-400',
        )}
      />
    </svg>
  );
}

function TimerRow({ timer, now, onCancel }: { timer: Timer; now: number; onCancel: () => void }) {
  const left = Math.max(0, Math.ceil((new Date(timer.ends_at).getTime() - now) / 1000));
  const done = left === 0;
  return (
    <li className="group flex items-center gap-3">
      <Ring progress={timerProgress(timer, now)} done={done} />
      <div className="min-w-0 flex-1">
        <p
          className={cn(
            'font-mono text-lg leading-none font-light tabular-nums',
            done ? 'animate-pulse text-gold-400' : 'text-white/90',
          )}
        >
          {done ? 'Done' : formatCountdown(left)}
        </p>
        <p className="mt-1 truncate text-[11.5px] text-white/45">
          {timer.label || formatCountdown(timer.duration_s, { words: true })}
        </p>
      </div>
      <button
        type="button"
        onClick={onCancel}
        aria-label={`Cancel ${timer.label || 'timer'}`}
        className="text-white/25 transition group-hover:text-white/50 hover:text-white/80"
      >
        <X className="size-4" />
      </button>
    </li>
  );
}

/** Countdown timers: start one here or by voice ("Jarvis, 10 minutes for the rice"). */
export function TimersWidget() {
  const { data, error, reload } = useCoreData(['timers'], coreApi.listTimers);
  const timers = data ?? [];
  const now = useNow(timers.length > 0);
  const [draft, setDraft] = useState('');
  const [problem, setProblem] = useState<string | null>(null);

  const start = async (text: string) => {
    setProblem(null);
    try {
      await coreApi.startTimer(text);
      setDraft('');
    } catch (reason) {
      setProblem(reason instanceof ApiError ? reason.message : "Couldn't start the timer.");
    }
    reload();
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (draft.trim()) void start(draft.trim());
  };

  const cancel = async (id: number) => {
    await coreApi.cancelTimer(id).catch(() => undefined);
    reload();
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <form onSubmit={submit} className="flex items-center gap-2">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="12 min tea"
          aria-label="New timer"
          className="h-8 min-w-0 flex-1 rounded-lg border border-white/8 bg-white/[0.03] px-3 text-[13px] text-white/85 placeholder:text-white/25 focus:border-arc-400/40 focus:outline-none"
        />
        <button
          type="submit"
          disabled={!draft.trim()}
          aria-label="Start timer"
          className="flex size-8 items-center justify-center rounded-lg bg-white/5 text-white/60 transition hover:bg-white/10 disabled:opacity-30"
        >
          <Play className="size-3.5" />
        </button>
      </form>
      {problem && <p className="-mt-1 text-[11px] text-signal-red/80">{problem}</p>}

      {error ? (
        <p className="text-xs text-signal-red/70">Couldn't load timers.</p>
      ) : timers.length === 0 ? (
        <div className="flex flex-1 flex-col justify-center gap-2.5">
          <div className="flex gap-1.5">
            {PRESETS.map((preset) => (
              <button
                key={preset}
                type="button"
                onClick={() => void start(preset)}
                className="flex-1 rounded-lg border border-white/8 py-1.5 font-mono text-[11px] text-white/55 transition hover:border-arc-400/40 hover:text-arc-200"
              >
                {preset}
              </button>
            ))}
          </div>
          <p className="text-[12px] text-white/30">Or say “Jarvis, 10 minutes for the rice”.</p>
        </div>
      ) : (
        <ul className="hud-scroll -mr-2 min-h-0 flex-1 space-y-3 overflow-y-auto pr-2">
          {timers.map((timer) => (
            <TimerRow
              key={timer.id}
              timer={timer}
              now={now}
              onCancel={() => void cancel(timer.id)}
            />
          ))}
        </ul>
      )}
    </div>
  );
}
