import { cn } from '../../lib/cn';

/** Semantic tone of a status indicator. */
export type Tone = 'ok' | 'warn' | 'error' | 'muted';

const TONES: Record<Tone, string> = {
  ok: 'bg-arc-400 shadow-[0_0_10px_rgb(var(--accent-rgb)/0.8)]',
  warn: 'bg-gold-400 shadow-[0_0_10px_rgb(var(--thinking-rgb)/0.7)]',
  error: 'bg-signal-red shadow-[0_0_10px_rgb(255_92_122/0.7)]',
  muted: 'bg-white/20',
};

/** A small glowing dot. Pulses for `ok` to signal a live link. */
export function StatusDot({
  tone,
  className,
}: {
  readonly tone: Tone;
  readonly className?: string;
}) {
  return (
    <span className={cn('relative inline-flex size-1.5', className)} aria-hidden>
      {tone === 'ok' && (
        <span className="absolute inline-flex size-full animate-ping rounded-full bg-arc-400 opacity-50" />
      )}
      <span className={cn('relative inline-flex size-1.5 rounded-full', TONES[tone])} />
    </span>
  );
}
