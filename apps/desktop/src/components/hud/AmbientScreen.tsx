import { AnimatePresence, motion } from 'motion/react';
import { useEffect, useState } from 'react';

import { pad2 } from '../../lib/time';
import { useUi } from '../../state/uiStore';

const dateFormat = new Intl.DateTimeFormat(undefined, {
  weekday: 'long',
  day: 'numeric',
  month: 'long',
});

/** A calm, dimmed clock that replaces the HUD while you're away. */
export function AmbientScreen() {
  const ambient = useUi((s) => s.ambient);
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    if (!ambient) return;
    const timer = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, [ambient]);

  return (
    <AnimatePresence>
      {ambient && (
        <motion.div
          key="ambient"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 1.2 }}
          className="fixed inset-0 z-30 flex flex-col items-center justify-center bg-void"
          aria-label="Ambient clock"
        >
          <div className="ambient-orb mb-14" aria-hidden />
          <p className="text-[clamp(5rem,14vw,11rem)] leading-none font-extralight tracking-tight text-white/85 tabular-nums">
            {pad2(now.getHours())}
            <span className="ambient-colon text-arc-400/70">:</span>
            {pad2(now.getMinutes())}
          </p>
          <p className="mt-6 font-mono text-xs tracking-[0.4em] text-white/30 uppercase">
            {dateFormat.format(now)}
          </p>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
