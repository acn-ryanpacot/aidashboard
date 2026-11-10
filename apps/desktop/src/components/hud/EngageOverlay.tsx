import { AnimatePresence, motion } from 'motion/react';
import { useState } from 'react';

import { useAssistant, useVoiceAssistant } from '../../core/voice/hooks';

/**
 * First-run screen. Browsers (and WebView2) only allow audio after a user
 * gesture, so the user "engages" Jarvis once per launch.
 */
export function EngageOverlay() {
  const assistant = useVoiceAssistant();
  const engaged = useAssistant((s) => s.engaged);
  const connection = useAssistant((s) => s.connection);
  const userName = useAssistant((s) => s.capabilities?.user_name);
  const [pending, setPending] = useState(false);

  const engage = async (withMicrophone: boolean) => {
    setPending(true);
    try {
      await assistant.engage(withMicrophone);
    } finally {
      setPending(false);
    }
  };

  return (
    <AnimatePresence>
      {!engaged && (
        <motion.div
          key="engage"
          initial={{ opacity: 1 }}
          exit={{ opacity: 0, scale: 1.04, filter: 'blur(12px)' }}
          transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
          className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-void/92 backdrop-blur-2xl"
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 1.2, ease: [0.22, 1, 0.36, 1] }}
            className="engage-core mb-12"
            aria-hidden
          />
          <motion.h1
            initial={{ opacity: 0, letterSpacing: '0.2em' }}
            animate={{ opacity: 1, letterSpacing: '0.6em' }}
            transition={{ duration: 1.4, delay: 0.2, ease: [0.22, 1, 0.36, 1] }}
            className="mb-3 pl-[0.6em] text-2xl font-light text-white/90"
          >
            JARVIS
          </motion.h1>
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.6 }}
            className="mb-12 font-mono text-[11px] tracking-[0.3em] text-white/40 uppercase"
          >
            {userName ? `Welcome back, ${userName}` : 'Personal intelligence system'}
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.8 }}
            className="flex flex-col items-center gap-4"
          >
            <button
              type="button"
              disabled={pending}
              onClick={() => void engage(true)}
              className="engage-button rounded-full px-10 py-3.5 text-sm font-medium tracking-[0.25em] text-void uppercase"
            >
              Engage
            </button>
            <button
              type="button"
              disabled={pending}
              onClick={() => void engage(false)}
              className="font-mono text-[11px] tracking-[0.2em] text-white/40 uppercase transition hover:text-white/70"
            >
              Continue without microphone
            </button>
          </motion.div>

          {connection === 'offline' && (
            <p className="absolute bottom-10 font-mono text-[11px] text-gold-400/80">
              Core service unreachable — start it with <code>pnpm dev:core</code>
            </p>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
