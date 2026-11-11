import { Bell, Info, type LucideIcon, Sunrise, Timer, TrendingUp, Trash2 } from 'lucide-react';
import { useEffect, useState } from 'react';

import { type NotificationItem, coreApi } from '../../core/api/client';
import { useCoreData } from '../../core/api/useCoreData';
import { cn } from '../../lib/cn';
import { groupByDayLabel, noticeLabel } from '../../lib/notices';
import { useUi } from '../../state/uiStore';
import { Modal } from '../ui/Modal';

const KIND_ICON: Partial<Record<string, LucideIcon>> = {
  timer: Timer,
  alert: TrendingUp,
  reminder: Bell,
  briefing: Sunrise,
};

const KIND_TONE: Partial<Record<string, string>> = {
  timer: 'text-gold-400 bg-gold-400/10',
  alert: 'text-signal-green bg-signal-green/10',
  reminder: 'text-arc-300 bg-arc-400/10',
  briefing: 'text-arc-200 bg-arc-400/10',
};

function clock(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
}

function Row({ item, fresh }: { item: NotificationItem; fresh: boolean }) {
  const Icon = KIND_ICON[item.kind] ?? Info;
  return (
    <li className="flex gap-3">
      <span
        className={cn(
          'mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full',
          KIND_TONE[item.kind] ?? 'bg-white/5 text-white/50',
        )}
      >
        <Icon className="size-3.5" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="flex items-baseline gap-2">
          <span className="font-mono text-[10px] tracking-[0.2em] text-white/45 uppercase">
            {noticeLabel(item.kind)}
          </span>
          <span className="font-mono text-[10px] text-white/30">{clock(item.created_at)}</span>
          {fresh && <span className="size-1.5 rounded-full bg-arc-400" aria-label="new" />}
        </p>
        <p
          className={cn(
            'mt-0.5 text-[13px] leading-snug',
            fresh ? 'text-white/90' : 'text-white/60',
          )}
        >
          {item.text}
        </p>
      </div>
    </li>
  );
}

/**
 * Everything Jarvis announced (timers, stock alerts, reminders, briefings),
 * so nothing is lost when you weren't at the desk. Opening it marks
 * everything read; what was new stays highlighted until it closes.
 */
export function NotificationsPanel() {
  const open = useUi((s) => s.overlay === 'notifications');
  const close = useUi((s) => s.close);
  const { data, reload } = useCoreData(['notifications'], coreApi.listNotifications);
  const [fresh, setFresh] = useState<ReadonlySet<number>>(() => new Set());

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    void coreApi
      .listNotifications(50)
      .then(async (current) => {
        if (cancelled) return;
        setFresh(new Set(current.items.filter((i) => !i.read).map((i) => i.id)));
        if (current.unread > 0) await coreApi.markNotificationsRead();
        reload();
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [open, reload]);

  const items = data?.items ?? [];
  const clear = async () => {
    await coreApi.clearNotifications().catch(() => undefined);
    reload();
  };

  const footer =
    items.length > 0 ? (
      <div className="flex items-center justify-between">
        <p className="text-[12px] text-white/40">Last 30 days</p>
        <button
          type="button"
          onClick={() => void clear()}
          className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-[12px] text-white/50 transition hover:bg-white/5 hover:text-white/80"
        >
          <Trash2 className="size-3.5" /> Clear history
        </button>
      </div>
    ) : undefined;

  return (
    <Modal open={open} onClose={close} title="Notifications" variant="drawer" footer={footer}>
      {items.length === 0 ? (
        <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
          <Bell className="size-6 text-white/20" />
          <p className="max-w-[16rem] text-[13px] leading-relaxed text-white/40">
            Nothing yet. Timers, reminders, stock alerts and briefings show up here, even when no
            window was open.
          </p>
        </div>
      ) : (
        <div className="space-y-6">
          {groupByDayLabel(items).map((group) => (
            <section key={group.label}>
              <h3 className="mb-3 font-mono text-[10px] tracking-[0.3em] text-arc-300/70 uppercase">
                {group.label}
              </h3>
              <ul className="space-y-4">
                {group.items.map((item) => (
                  <Row key={item.id} item={item} fresh={fresh.has(item.id)} />
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </Modal>
  );
}
