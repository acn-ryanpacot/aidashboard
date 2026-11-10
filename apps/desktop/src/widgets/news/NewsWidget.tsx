import type { WidgetProps } from '@jarvis/widget-sdk';

import { coreApi } from '../../core/api/client';
import { useCoreData } from '../../core/api/useCoreData';
import { headlineAge } from '../../lib/format';

const loadNews = () => coreApi.getNews(8);

/** Latest headlines from the feeds configured in Settings. */
export function NewsWidget({ size }: WidgetProps) {
  const { data, error, loaded } = useCoreData(['settings'], loadNews, 15 * 60_000);
  const items = (data ?? []).slice(0, size.rows >= 3 ? 7 : 4);

  if (error || (loaded && items.length === 0)) {
    return (
      <p className="m-auto text-xs text-white/35">No headlines — check your feeds in Settings.</p>
    );
  }
  return (
    <ol className="hud-scroll -mr-2 flex-1 space-y-2.5 overflow-y-auto pr-2">
      {items.map((headline) => (
        <li key={headline.url || headline.title} className="flex gap-3">
          <span className="w-7 shrink-0 pt-0.5 text-right font-mono text-[10px] text-white/30">
            {headlineAge(headline.published)}
          </span>
          <a
            href={headline.url}
            target="_blank"
            rel="noreferrer"
            className="line-clamp-2 text-[13px] leading-snug text-white/80 transition hover:text-arc-200"
            title={headline.source}
          >
            {headline.title}
          </a>
        </li>
      ))}
    </ol>
  );
}
