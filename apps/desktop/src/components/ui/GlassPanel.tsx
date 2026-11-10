import type { HTMLAttributes, ReactNode } from 'react';

import { cn } from '../../lib/cn';

interface Props extends HTMLAttributes<HTMLElement> {
  /** Small uppercase label in the panel header. */
  readonly title?: string;
  /** Optional element on the right of the header (badge, action…). */
  readonly accessory?: ReactNode;
  readonly children: ReactNode;
}

/** The frosted-glass surface every HUD panel and widget sits on. */
export function GlassPanel({ title, accessory, className, children, ...rest }: Props) {
  return (
    <section className={cn('glass relative flex flex-col overflow-hidden', className)} {...rest}>
      {title && (
        <header className="flex items-center justify-between px-5 pt-4 pb-2">
          <h2 className="font-mono text-[10px] tracking-[0.28em] text-white/45 uppercase">
            {title}
          </h2>
          {accessory}
        </header>
      )}
      <div className="flex min-h-0 flex-1 flex-col px-5 pb-5">{children}</div>
    </section>
  );
}
