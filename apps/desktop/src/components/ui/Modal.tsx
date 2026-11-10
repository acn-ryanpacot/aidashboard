import { X } from 'lucide-react';
import { AnimatePresence, motion } from 'motion/react';
import { type ReactNode, useEffect, useId } from 'react';

import { cn } from '../../lib/cn';

interface Props {
  readonly open: boolean;
  readonly onClose: () => void;
  readonly title: string;
  readonly children: ReactNode;
  /** `dialog` = centred card; `drawer` = slides in from the right. */
  readonly variant?: 'dialog' | 'drawer';
  readonly footer?: ReactNode;
}

/** Accessible modal surface: Esc and backdrop click close it. */
export function Modal({ open, onClose, title, children, variant = 'dialog', footer }: Props) {
  const titleId = useId();

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation();
        onClose();
      }
    };
    window.addEventListener('keydown', onKey, true);
    return () => window.removeEventListener('keydown', onKey, true);
  }, [open, onClose]);

  const drawer = variant === 'drawer';
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          key="modal"
          className={cn(
            'fixed inset-0 z-40 flex bg-void/60 backdrop-blur-md',
            drawer ? 'justify-end' : 'items-start justify-center pt-[12vh]',
          )}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) onClose();
          }}
        >
          <motion.section
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            initial={drawer ? { x: 40, opacity: 0 } : { y: 12, opacity: 0, scale: 0.98 }}
            animate={drawer ? { x: 0, opacity: 1 } : { y: 0, opacity: 1, scale: 1 }}
            exit={drawer ? { x: 40, opacity: 0 } : { y: 8, opacity: 0 }}
            transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
            className={cn(
              'glass flex flex-col overflow-hidden',
              drawer
                ? 'h-full w-[min(100vw,34rem)] rounded-none rounded-l-3xl'
                : 'max-h-[72vh] w-[min(92vw,40rem)]',
            )}
          >
            <header className="flex items-center justify-between border-b border-white/5 px-6 py-4">
              <h2
                id={titleId}
                className="font-mono text-[11px] tracking-[0.28em] text-white/60 uppercase"
              >
                {title}
              </h2>
              <button
                type="button"
                onClick={onClose}
                aria-label="Close"
                className="flex size-8 items-center justify-center rounded-lg text-white/40 transition hover:bg-white/5 hover:text-white/80"
              >
                <X className="size-4" />
              </button>
            </header>
            <div className="hud-scroll min-h-0 flex-1 overflow-y-auto px-6 py-5">{children}</div>
            {footer && <footer className="border-t border-white/5 px-6 py-4">{footer}</footer>}
          </motion.section>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
