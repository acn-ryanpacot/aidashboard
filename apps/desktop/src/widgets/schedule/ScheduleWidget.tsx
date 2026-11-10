import { coreApi } from '../../core/api/client';
import { useCoreData } from '../../core/api/useCoreData';
import { cn } from '../../lib/cn';
import { groupByDay } from '../../lib/format';
import { useUi } from '../../state/uiStore';

const loadCalendar = () => coreApi.getCalendar(2);

const timeFormat = new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' });

/** Today's and tomorrow's events from the calendars connected in Settings. */
export function ScheduleWidget() {
  const { data, error } = useCoreData(['settings'], loadCalendar, 5 * 60_000);
  const openSettings = useUi((s) => s.open);

  if (error) return <p className="m-auto text-xs text-white/35">Calendar unavailable.</p>;
  if (data && !data.configured) {
    return (
      <button
        type="button"
        onClick={() => openSettings('settings')}
        className="m-auto max-w-[15rem] text-center text-[13px] leading-relaxed text-white/40 hover:text-white/70"
      >
        Connect a calendar: paste its private ICS address in Settings → Briefing.
      </button>
    );
  }
  const groups = groupByDay(data?.events ?? []);
  if (data && groups.length === 0) {
    return <p className="m-auto text-[13px] text-white/35">Nothing scheduled. Enjoy the calm.</p>;
  }
  const now = Date.now();
  return (
    <div className="hud-scroll -mr-2 flex-1 space-y-3 overflow-y-auto pr-2">
      {groups.map((group) => (
        <section key={group.label}>
          <h3 className="mb-1.5 font-mono text-[9px] tracking-[0.3em] text-white/30 uppercase">
            {group.label}
          </h3>
          <ul className="space-y-1.5">
            {group.events.map((event) => {
              const live =
                new Date(event.start).getTime() <= now && new Date(event.end).getTime() > now;
              return (
                <li key={`${event.start}-${event.title}`} className="flex items-baseline gap-3">
                  <span
                    className={cn(
                      'w-14 shrink-0 font-mono text-[11px] tabular-nums',
                      live ? 'text-arc-300' : 'text-white/40',
                    )}
                  >
                    {event.all_day ? 'All day' : timeFormat.format(new Date(event.start))}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13px] text-white/85">{event.title}</span>
                    {event.location && (
                      <span className="block truncate text-[11px] text-white/35">
                        {event.location}
                      </span>
                    )}
                  </span>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );
}
