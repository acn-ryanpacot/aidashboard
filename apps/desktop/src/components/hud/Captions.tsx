import { AnimatePresence, motion } from 'motion/react';
import { useEffect, useState } from 'react';

import { useAssistant, useVoiceAssistant } from '../../core/voice/hooks';
import { wakePhrase } from '../../core/voice/protocol';
import type { SpeechSegmentMessage } from '../../core/voice/protocol';
import { cn } from '../../lib/cn';

interface CaptionView {
  readonly segment: SpeechSegmentMessage;
  readonly wordIndex: number;
}

/** Track the caption at display rate, re-rendering only when the word changes. */
function useLiveCaption(): CaptionView | null {
  const assistant = useVoiceAssistant();
  const [view, setView] = useState<CaptionView | null>(null);

  useEffect(() => {
    let frameId = 0;
    let lastKey = '';
    const tick = () => {
      const caption = assistant.activeCaption();
      // Between two sentences there can be a short gap; keep the last caption.
      if (!caption && assistant.store.getState().state === 'speaking') {
        frameId = requestAnimationFrame(tick);
        return;
      }
      const key = caption ? `${caption.segment.segment_id}:${caption.wordIndex}` : '';
      if (key !== lastKey) {
        lastKey = key;
        setView(caption);
      }
      frameId = requestAnimationFrame(tick);
    };
    frameId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frameId);
  }, [assistant]);

  return view;
}

/** `true` for a few seconds after the server ignored an unrecognised voice. */
function useRecentlyRejected(durationMs = 2500): boolean {
  const rejectedAt = useAssistant((s) => s.rejectedAt);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    if (rejectedAt === null) return;
    setVisible(true);
    const timer = setTimeout(() => setVisible(false), durationMs);
    return () => clearTimeout(timer);
  }, [rejectedAt, durationMs]);
  return visible;
}

/** Karaoke-style subtitles under the orb, or a contextual hint when silent. */
export function Captions() {
  const caption = useLiveCaption();
  const state = useAssistant((s) => s.state);
  const capabilities = useAssistant((s) => s.capabilities);
  const lastUser = useAssistant((s) => s.entries.findLast((e) => e.speaker === 'user')?.text);
  const activeTool = useAssistant((s) => s.activeTool);
  const rejected = useRecentlyRejected();

  const phrase = capabilities?.wake_word_enabled ? wakePhrase(capabilities.wake_model) : null;
  const hint =
    state === 'listening'
      ? 'Listening…'
      : state === 'thinking'
        ? `${activeTool ?? 'Thinking'}…`
        : rejected
          ? 'Voice not recognised'
          : phrase
            ? `Say “${phrase}”, tap the core, or Ctrl+Space`
            : 'Tap the core, press Ctrl+Space, or type below';

  return (
    <div className="flex min-h-[7.5rem] w-full max-w-3xl flex-col items-center gap-3 text-center">
      <AnimatePresence mode="wait">
        {lastUser && (state === 'thinking' || state === 'speaking') && (
          <motion.p
            key={lastUser}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="max-w-2xl truncate font-mono text-xs tracking-wide text-white/40"
          >
            “{lastUser}”
          </motion.p>
        )}
      </AnimatePresence>

      <AnimatePresence mode="wait">
        {caption ? (
          <motion.p
            key={caption.segment.segment_id}
            initial={{ opacity: 0, y: 8, filter: 'blur(6px)' }}
            animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
            exit={{ opacity: 0, y: -6, filter: 'blur(6px)' }}
            transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
            className="text-2xl leading-relaxed font-light tracking-tight text-balance"
            aria-live="polite"
          >
            {caption.segment.words.length > 0
              ? caption.segment.words.map((word, i) => (
                  <span
                    key={`${i}-${word.word}`}
                    className={cn(
                      'transition-[color,text-shadow] duration-150',
                      i < caption.wordIndex && 'text-white/85',
                      i === caption.wordIndex &&
                        'text-arc-200 [text-shadow:0_0_18px_rgb(var(--accent-rgb)/0.65)]',
                      i > caption.wordIndex && 'text-white/25',
                    )}
                  >
                    {word.word}{' '}
                  </span>
                ))
              : caption.segment.text}
          </motion.p>
        ) : (
          <motion.p
            key={hint}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className={cn(
              'font-mono text-xs tracking-[0.3em] text-white/35 uppercase',
              state === 'thinking' && 'shimmer-text',
            )}
          >
            {hint}
          </motion.p>
        )}
      </AnimatePresence>
    </div>
  );
}
