import { Sunrise } from 'lucide-react';
import { useEffect, useState } from 'react';

import { DEFAULT_USER_NAME } from '../../config';
import { useAssistant, useVoiceAssistant } from '../../core/voice/hooks';
import { pad2, partOfDayGreeting } from '../../lib/time';

/** Re-render every second, aligned to the wall clock. */
function useNow(): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    const schedule = () => {
      timer = setTimeout(
        () => {
          setNow(new Date());
          schedule();
        },
        1000 - (Date.now() % 1000),
      );
    };
    schedule();
    return () => clearTimeout(timer);
  }, []);
  return now;
}

const dateFormat = new Intl.DateTimeFormat(undefined, {
  weekday: 'long',
  day: 'numeric',
  month: 'long',
});

/** Large time readout with a personal greeting. */
export function ClockWidget() {
  const now = useNow();
  const assistant = useVoiceAssistant();
  const online = useAssistant((s) => s.connection === 'online');
  const userName = useAssistant((s) => s.capabilities?.user_name ?? DEFAULT_USER_NAME);

  return (
    <div className="flex flex-1 flex-col justify-end">
      <p className="text-sm text-white/45">
        {partOfDayGreeting(now.getHours())}, <span className="text-white/80">{userName}</span>
      </p>
      <p className="mt-1 flex items-baseline gap-2 tabular-nums">
        <span className="text-[56px] leading-none font-extralight tracking-tight text-white">
          {pad2(now.getHours())}
          <span className="text-arc-400/80">:</span>
          {pad2(now.getMinutes())}
        </span>
        <span className="font-mono text-sm text-arc-300/60">{pad2(now.getSeconds())}</span>
      </p>
      <div className="mt-2 flex items-center justify-between">
        <p className="font-mono text-[11px] tracking-[0.2em] text-white/35 uppercase">
          {dateFormat.format(now)}
        </p>
        <button
          type="button"
          disabled={!online}
          onClick={() => assistant.ask('Give me my briefing.')}
          className="flex items-center gap-1.5 rounded-full border border-white/10 px-2.5 py-1 font-mono text-[9px] tracking-[0.18em] text-white/45 uppercase transition hover:border-arc-400/50 hover:text-arc-200 disabled:opacity-30"
          title="Spoken briefing: weather, calendar, tasks, headlines"
        >
          <Sunrise className="size-3" /> Brief me
        </button>
      </div>
    </div>
  );
}
