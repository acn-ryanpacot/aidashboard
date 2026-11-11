import type { WidgetProps } from '@jarvis/widget-sdk';
import { BellRing } from 'lucide-react';

import {
  type PisoTiyempoResponse,
  type PortfolioHolding,
  type StockAlert,
  type StockIdea,
  coreApi,
} from '../../core/api/client';
import { useCoreData } from '../../core/api/useCoreData';
import { cn } from '../../lib/cn';
import {
  formatPercent,
  formatPesos,
  formatSession,
  formatTradingDate,
  moveColor,
} from '../../lib/format';

const loadPortfolio = () => coreApi.getPisoTiyempo();

/** Prices update once a day (after PisoTiyempo syncs), so a slow refresh is plenty. */
const REFRESH_MS = 5 * 60_000;

function Caption({ children }: { children: string }) {
  return (
    <p className="font-mono text-[10px] tracking-[0.18em] text-white/40 uppercase">{children}</p>
  );
}

function Notice({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="m-auto max-w-[17rem] text-center">
      <p className="text-[13px] text-white/70">{title}</p>
      <p className="mt-1 text-[11px] leading-relaxed text-white/35">{detail}</p>
    </div>
  );
}

function HoldingRow({ holding }: { holding: PortfolioHolding }) {
  return (
    <li className="flex items-baseline gap-3 text-[13px]">
      <span className="w-14 shrink-0 font-medium tracking-wide text-white/85">
        {holding.symbol}
      </span>
      <span className="flex-1 font-mono text-[11px] text-white/45 tabular-nums">
        {holding.last_price !== null ? formatPesos(holding.last_price, { decimals: 2 }) : '—'}
      </span>
      <span
        className={cn(
          'w-16 text-right font-mono text-[11px] tabular-nums',
          moveColor(holding.change_pct),
        )}
      >
        {formatPercent(holding.change_pct)}
      </span>
      <span
        className={cn(
          'w-20 text-right font-mono text-[11px] tabular-nums',
          moveColor(holding.day_change),
        )}
      >
        {formatPesos(holding.day_change, { signed: true })}
      </span>
    </li>
  );
}

function Holdings({ data, rows }: { data: PisoTiyempoResponse; rows: number }) {
  const totals = data.totals;
  if (!totals) return null;
  const visible = data.holdings.slice(0, rows >= 3 ? 8 : 3);
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <div>
        <Caption>{formatSession(data.session_date, data.is_today)}</Caption>
        <div className="mt-1 flex items-baseline gap-3">
          <span
            className={cn(
              'text-2xl font-light tracking-tight tabular-nums',
              moveColor(totals.day_change),
            )}
          >
            {formatPesos(totals.day_change, { signed: true })}
          </span>
          <span className={cn('font-mono text-[12px] tabular-nums', moveColor(totals.day_change))}>
            {formatPercent(totals.day_change_pct)}
          </span>
        </div>
        <p className="mt-0.5 font-mono text-[10.5px] text-white/40 tabular-nums">
          Value {formatPesos(totals.market_value)} · P/L{' '}
          <span className={moveColor(totals.unrealized_pnl)}>
            {formatPesos(totals.unrealized_pnl, { signed: true })} (
            {formatPercent(totals.unrealized_pct, 1)})
          </span>
        </p>
      </div>
      <ul className="hud-scroll -mr-2 min-h-0 flex-1 space-y-1.5 overflow-y-auto border-t border-white/5 pt-2.5 pr-2">
        {visible.map((holding) => (
          <HoldingRow key={holding.symbol} holding={holding} />
        ))}
      </ul>
    </div>
  );
}

function IdeaCard({ idea, rank }: { idea: StockIdea; rank: number }) {
  // Every idea is in an uptrend (the caption says so) and the score has its own
  // badge, so the card lists only what sets this stock apart.
  const reasons = idea.reasons.filter((r) => !r.startsWith('Score') && !r.startsWith('Uptrend'));
  return (
    <li className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-3 py-2">
      <div className="flex items-baseline gap-2">
        <span className="font-mono text-[10px] text-white/30">{rank}</span>
        <span className="font-medium tracking-wide text-white/90">{idea.symbol}</span>
        <span className="truncate text-[11px] text-white/40" title={idea.name}>
          {idea.name}
        </span>
        <span className="ml-auto shrink-0 font-mono text-[11px] text-white/60 tabular-nums">
          {formatPesos(idea.close, { decimals: 2 })}
        </span>
        <span
          className="shrink-0 rounded-full border border-arc-400/30 px-1.5 font-mono text-[10px] text-arc-200 tabular-nums"
          title="PisoTiyempo score (−100 to +100)"
        >
          {idea.score > 0 ? `+${idea.score}` : idea.score}
        </span>
      </div>
      <p className="mt-1 text-[11px] leading-snug text-white/45">{reasons.join(' · ')}</p>
    </li>
  );
}

function Ideas({ data }: { data: PisoTiyempoResponse }) {
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2.5">
      <Caption>
        {['Uptrend ideas', formatTradingDate(data.session_date)].filter(Boolean).join(' · ')}
      </Caption>
      {data.ideas.length === 0 ? (
        <Notice
          title="No stock passes the trend-and-value screen today."
          detail={`Looking for stocks that are ${data.screen}.`}
        />
      ) : (
        <ol className="hud-scroll -mr-2 min-h-0 flex-1 space-y-2 overflow-y-auto pr-2">
          {data.ideas.map((idea, index) => (
            <IdeaCard key={idea.symbol} idea={idea} rank={index + 1} />
          ))}
        </ol>
      )}
      <p className="text-[10px] text-white/30" title={`Screen: ${data.screen}`}>
        {data.disclaimer}
      </p>
    </div>
  );
}

/** PSE portfolio from PisoTiyempo, or three ideas to research when you hold nothing. */
export function PortfolioWidget({ size }: WidgetProps) {
  // "portfolio" is announced when new PisoTiyempo alerts are spoken.
  const { data, error } = useCoreData(['settings', 'portfolio'], loadPortfolio, REFRESH_MS);

  if (error) return <Notice title="Portfolio unavailable" detail={error} />;
  if (!data) return null;
  if (data.status === 'disabled') {
    return (
      <Notice
        title="Portfolio is turned off"
        detail="Set JARVIS_PORTFOLIO_ENABLED=true in services/core/.env and restart the core."
      />
    );
  }
  if (data.status === 'unavailable') {
    return (
      <Notice
        title="PisoTiyempo isn't running"
        detail="Open the PisoTiyempo desktop app and let it sync. Its feed must be on port 8766 (see the PisoTiyempo guide)."
      />
    );
  }
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2.5">
      <Alerts alerts={data.alerts} />
      {data.holdings.length > 0 ? <Holdings data={data} rows={size.rows} /> : <Ideas data={data} />}
    </div>
  );
}

/** Your PisoTiyempo alerts that triggered at the latest close (also spoken once). */
function Alerts({ alerts }: { alerts: readonly StockAlert[] }) {
  if (alerts.length === 0) return null;
  const [first, ...rest] = alerts;
  return (
    <div
      className="flex items-start gap-2 rounded-lg border border-gold-400/20 bg-gold-400/[0.06] px-2.5 py-1.5"
      title={alerts.map((a) => a.message).join('\n')}
    >
      <BellRing className="mt-px size-3.5 shrink-0 text-gold-400/80" />
      <p className="min-w-0 flex-1 truncate text-[11.5px] text-white/75">{first?.message}</p>
      {rest.length > 0 && (
        <span className="shrink-0 font-mono text-[10px] text-gold-400/80">+{rest.length}</span>
      )}
    </div>
  );
}
