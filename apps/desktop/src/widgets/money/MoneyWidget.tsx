import type { WidgetProps } from '@jarvis/widget-sdk';
import { Eye, EyeOff, RotateCw } from 'lucide-react';
import { useState } from 'react';

import { type MoneyResponse, type Payment, coreApi } from '../../core/api/client';
import { useCoreData } from '../../core/api/useCoreData';
import { cn } from '../../lib/cn';
import {
  HIDDEN_AMOUNT,
  type DueTone,
  dueLabel,
  dueTone,
  dueTotal,
  formatDueDate,
  formatMoney,
} from '../../lib/money';

const loadMoney = () => coreApi.getMoney();

/** Due dates move at midnight and files change rarely; re-read every 10 minutes. */
const REFRESH_MS = 10 * 60_000;
/** The "Due soon" view covers this many days. */
const DUE_WINDOW_DAYS = 14;
const HIDE_KEY = 'jarvis.money.hidden';

type View = 'due' | 'debts';

const TONE: Record<DueTone, string> = {
  overdue: 'border-signal-red/40 bg-signal-red/10 text-signal-red',
  soon: 'border-gold-400/35 bg-gold-400/10 text-gold-400',
  later: 'border-white/10 text-white/45',
};

function usePersistentFlag(key: string): [boolean, () => void] {
  const [value, setValue] = useState(() => {
    try {
      return localStorage.getItem(key) === '1';
    } catch {
      return false;
    }
  });
  const toggle = () =>
    setValue((current) => {
      try {
        localStorage.setItem(key, current ? '0' : '1');
      } catch {
        // Private mode: the toggle still works for this session.
      }
      return !current;
    });
  return [value, toggle];
}

function Notice({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="m-auto max-w-[17rem] text-center">
      <p className="text-[13px] text-white/70">{title}</p>
      <p className="mt-1 text-[11px] leading-relaxed text-white/35">{detail}</p>
    </div>
  );
}

function Tab({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        'rounded-full px-2.5 py-0.5 font-mono text-[10px] tracking-[0.14em] uppercase transition',
        active ? 'bg-white/[0.07] text-arc-200' : 'text-white/35 hover:text-white/70',
      )}
    >
      {children}
    </button>
  );
}

function PaymentRow({
  payment,
  money,
  reminderDays,
}: {
  payment: Payment;
  money: (value: number) => string;
  reminderDays: number;
}) {
  const tone = dueTone(payment.days, reminderDays);
  return (
    <li className="flex items-center gap-2.5">
      <span
        className={cn(
          'w-[4.9rem] shrink-0 rounded-full border px-1.5 py-px text-center font-mono text-[10px] tabular-nums',
          TONE[tone],
        )}
      >
        {dueLabel(payment.days)}
      </span>
      <span className="min-w-0 flex-1" title={payment.file}>
        <span className="block truncate text-[13px] leading-tight text-white/85">
          {payment.name}
        </span>
        <span className="block font-mono text-[10px] leading-tight text-white/35">
          {formatDueDate(payment.due)}
          {payment.kind === 'debt' ? ' · debt payment' : payment.recurring ? ' · monthly' : ''}
        </span>
      </span>
      <span className="shrink-0 text-right font-mono text-[12px] text-white/80 tabular-nums">
        {payment.amount !== null ? money(payment.amount) : '—'}
      </span>
    </li>
  );
}

function DueSoon({ data, money }: { data: MoneyResponse; money: (value: number) => string }) {
  const due = data.payments.filter((p) => p.days <= DUE_WINDOW_DAYS);
  const overdue = due.filter((p) => p.days < 0).length;
  if (data.payments.length === 0) {
    return (
      <Notice
        title="No due dates found."
        detail="Add a Due date or Due day column to your bills or debts sheet (e.g. 2026-11-20, or 15 for monthly)."
      />
    );
  }
  const next = data.payments[0];
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2.5">
      <div>
        <p className="font-mono text-[10px] tracking-[0.18em] text-white/40 uppercase">
          Next {DUE_WINDOW_DAYS} days
        </p>
        <div className="mt-1 flex items-baseline gap-2">
          <span className="text-2xl font-light tracking-tight text-white/90 tabular-nums">
            {money(dueTotal(data.payments, DUE_WINDOW_DAYS))}
          </span>
          <span className="font-mono text-[11px] text-white/40">
            {due.length} payment{due.length === 1 ? '' : 's'}
            {overdue > 0 && <span className="text-signal-red"> · {overdue} overdue</span>}
          </span>
        </div>
      </div>
      {due.length === 0 && next ? (
        <p className="text-[12px] text-white/50">
          Nothing due soon. Next: <span className="text-white/80">{next.name}</span>{' '}
          {formatDueDate(next.due)}.
        </p>
      ) : (
        <ul className="hud-scroll -mr-2 min-h-0 flex-1 space-y-2 overflow-y-auto border-t border-white/5 pt-2.5 pr-2">
          {due.map((payment) => (
            <PaymentRow
              key={`${payment.file}|${payment.name}|${payment.due}`}
              payment={payment}
              money={money}
              reminderDays={data.reminder_days}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function Debts({ data, money }: { data: MoneyResponse; money: (value: number) => string }) {
  if (data.debts.length === 0) {
    return (
      <Notice
        title="No debts sheet found."
        detail="A sheet with a Balance column (and optionally Monthly, Rate and Due day) appears here."
      />
    );
  }
  const largest = data.debts[0]?.balance ?? 1;
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2.5">
      <div>
        <p className="font-mono text-[10px] tracking-[0.18em] text-white/40 uppercase">
          Total owed
        </p>
        <p className="mt-1 text-2xl font-light tracking-tight text-white/90 tabular-nums">
          {money(data.total_owed)}
        </p>
        <p className="mt-0.5 font-mono text-[10.5px] text-white/40 tabular-nums">
          {data.debts.length} debt{data.debts.length === 1 ? '' : 's'}
          {data.monthly_total > 0 && <> · {money(data.monthly_total)} a month</>}
        </p>
      </div>
      <ul className="hud-scroll -mr-2 min-h-0 flex-1 space-y-2 overflow-y-auto border-t border-white/5 pt-2.5 pr-2">
        {data.debts.map((debt) => (
          <li key={`${debt.file}|${debt.name}`} title={debt.file}>
            <div className="flex items-baseline gap-2 text-[13px]">
              <span className="min-w-0 flex-1 truncate text-white/85">{debt.name}</span>
              {debt.rate !== null && (
                <span className="shrink-0 font-mono text-[10px] text-white/35">
                  {Number(debt.rate.toFixed(2))}%
                </span>
              )}
              <span className="shrink-0 font-mono text-[12px] text-white/80 tabular-nums">
                {money(debt.balance)}
              </span>
            </div>
            <div className="mt-1 h-[3px] overflow-hidden rounded-full bg-white/[0.05]">
              <div
                className="h-full rounded-full bg-arc-400/50"
                style={{ width: `${Math.max(3, (debt.balance / largest) * 100)}%` }}
              />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Debts and bills from the user's own spreadsheets: what's due in the next
 * two weeks (gold inside the reminder window, red when overdue) and what's
 * owed. Amounts can be hidden with the eye button, e.g. while screen sharing.
 */
export function MoneyWidget(_props: WidgetProps) {
  const { data, error, reload } = useCoreData(['money', 'settings'], loadMoney, REFRESH_MS);
  const [hidden, toggleHidden] = usePersistentFlag(HIDE_KEY);
  const [chosen, setView] = useState<View | null>(null);

  if (error) return <Notice title="Money unavailable" detail={error} />;
  if (!data) return null;
  if (data.status === 'disabled') {
    return (
      <Notice
        title="Needs document search"
        detail="Turn on tools and install the embedding model (ollama pull nomic-embed-text), then restart the core."
      />
    );
  }
  if (data.status === 'no_folder') {
    return (
      <Notice
        title="Choose your documents folder"
        detail="Settings → Knowledge → Documents folder. Put your debts and bills spreadsheets in it."
      />
    );
  }
  if (data.status === 'no_sheets') {
    return (
      <Notice
        title="Add a debts or bills spreadsheet"
        detail="Debts: Creditor · Balance · Monthly · Due day. Bills: Bill · Amount · Due date. Excel or CSV, in your documents folder."
      />
    );
  }

  const view: View = chosen ?? (data.payments.length > 0 ? 'due' : 'debts');
  const money = (value: number) => (hidden ? HIDDEN_AMOUNT : formatMoney(value, data.currency));
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2.5">
      <div className="flex items-center gap-1">
        <Tab active={view === 'due'} onClick={() => setView('due')}>
          Due soon
        </Tab>
        <Tab active={view === 'debts'} onClick={() => setView('debts')}>
          Debts
        </Tab>
        <button
          type="button"
          onClick={reload}
          aria-label="Refresh"
          title={`From ${data.sources.join(', ')}`}
          className="ml-auto rounded-md p-1 text-white/30 transition hover:text-white/70"
        >
          <RotateCw className="size-3" />
        </button>
        <button
          type="button"
          onClick={toggleHidden}
          aria-label={hidden ? 'Show amounts' : 'Hide amounts'}
          aria-pressed={hidden}
          className="rounded-md p-1 text-white/30 transition hover:text-white/70"
        >
          {hidden ? <EyeOff className="size-3.5" /> : <Eye className="size-3.5" />}
        </button>
      </div>
      {view === 'due' ? <DueSoon data={data} money={money} /> : <Debts data={data} money={money} />}
    </div>
  );
}
