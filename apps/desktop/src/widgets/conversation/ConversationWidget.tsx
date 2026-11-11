import { useEffect, useRef } from 'react';

import { DEFAULT_USER_NAME } from '../../config';
import { useAssistant } from '../../core/voice/hooks';
import { cn } from '../../lib/cn';
import { noticeLabel } from '../../lib/notices';

const SPEAKER_LABEL: Partial<Record<string, string>> = { system: 'System' };

/** Scrolling transcript of the current session. */
export function ConversationWidget() {
  const entries = useAssistant((s) => s.entries);
  const userName = useAssistant((s) => s.capabilities?.user_name ?? DEFAULT_USER_NAME);
  const assistantName = useAssistant((s) => s.capabilities?.assistant_name ?? 'Jarvis');
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [entries]);

  if (entries.length === 0) {
    return (
      <p className="m-auto max-w-[16rem] text-center text-sm leading-relaxed text-white/30">
        Your conversation with {assistantName} will appear here.
      </p>
    );
  }

  return (
    <div className="hud-scroll -mr-2 flex-1 space-y-4 overflow-y-auto pr-2">
      {entries.map((entry) => (
        <article key={entry.id} className="space-y-1">
          <h3
            className={cn(
              'font-mono text-[9px] tracking-[0.3em] uppercase',
              entry.speaker === 'user' && 'text-white/35',
              entry.speaker === 'assistant' && 'text-arc-300/70',
              entry.speaker === 'system' && 'text-signal-red/80',
              entry.speaker === 'notice' && 'text-gold-400/80',
            )}
          >
            {entry.speaker === 'notice'
              ? noticeLabel(entry.kind)
              : (SPEAKER_LABEL[entry.speaker] ??
                (entry.speaker === 'user' ? userName : assistantName))}
          </h3>
          <p
            className={cn(
              'text-[13.5px] leading-relaxed',
              entry.speaker === 'user' ? 'text-white/60' : 'text-white/85',
              entry.isError && 'text-signal-red/90',
            )}
          >
            {entry.text}
            {entry.streaming && <span className="caret" aria-hidden />}
          </p>
        </article>
      ))}
      <div ref={endRef} />
    </div>
  );
}
