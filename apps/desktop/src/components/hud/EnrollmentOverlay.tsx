import { AnimatePresence, motion } from 'motion/react';
import { useEffect } from 'react';

import { useAssistant, useVoiceAssistant } from '../../core/voice/hooks';
import { cn } from '../../lib/cn';

const PROMPTS = [
  'Tell me about your plans for the weekend.',
  'Describe the room you are sitting in.',
  'What did you have for breakfast today?',
  'Read the time on the clock out loud.',
  'Name three places you would like to visit.',
];

const OUTCOME: Record<string, string> = {
  complete: 'Voiceprint saved. I will answer only you from now on.',
  cancelled: 'Voice training cancelled.',
  failed: 'Voice training failed — please try again.',
};

/** Guides the user through recording voice-ID samples. */
export function EnrollmentOverlay() {
  const assistant = useVoiceAssistant();
  const enrollment = useAssistant((s) => s.enrollment);
  const state = useAssistant((s) => s.state);
  const userName = useAssistant((s) => s.capabilities?.user_name ?? '');
  const recording = enrollment?.status === 'recording';

  useEffect(() => {
    if (!enrollment || recording) return;
    const timer = setTimeout(() => assistant.dismissEnrollment(), 2600);
    return () => clearTimeout(timer);
  }, [assistant, enrollment, recording]);

  return (
    <AnimatePresence>
      {enrollment && (
        <motion.div
          key="enrollment"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-40 flex items-center justify-center bg-void/70 backdrop-blur-xl"
          role="dialog"
          aria-modal="true"
          aria-label="Voice ID training"
        >
          <motion.div
            initial={{ y: 12, scale: 0.98 }}
            animate={{ y: 0, scale: 1 }}
            className="glass w-[min(92vw,30rem)] p-8 text-center"
          >
            <p className="font-mono text-[10px] tracking-[0.3em] text-arc-300/70 uppercase">
              Voice ID training
            </p>
            {recording ? (
              <>
                <h2 className="mt-4 text-xl font-light text-white/90">
                  {userName ? `${userName}, say` : 'Say'} this naturally:
                </h2>
                <p className="mt-3 text-lg leading-relaxed text-arc-100">
                  “{PROMPTS[enrollment.collected % PROMPTS.length]}”
                </p>
                <div className="mt-6 flex justify-center gap-2" aria-hidden>
                  {Array.from({ length: enrollment.required }, (_, i) => (
                    <span
                      key={i}
                      className={cn(
                        'h-1.5 w-8 rounded-full transition-colors duration-500',
                        i < enrollment.collected
                          ? 'bg-arc-400'
                          : i === enrollment.collected && state === 'listening'
                            ? 'animate-pulse bg-arc-400/50'
                            : 'bg-white/10',
                      )}
                    />
                  ))}
                </div>
                <p className="mt-3 font-mono text-[11px] text-white/35">
                  Sample {Math.min(enrollment.collected + 1, enrollment.required)} of{' '}
                  {enrollment.required}
                </p>
                <button
                  type="button"
                  onClick={() => assistant.cancel()}
                  className="mt-6 font-mono text-[11px] tracking-[0.2em] text-white/40 uppercase transition hover:text-white/70"
                >
                  Cancel
                </button>
              </>
            ) : (
              <p className="mt-5 text-lg font-light text-white/85">{OUTCOME[enrollment.status]}</p>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
