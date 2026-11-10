import { CornerDownLeft, MessageSquare, Search } from 'lucide-react';
import { AnimatePresence, motion } from 'motion/react';
import { useEffect, useMemo, useRef, useState } from 'react';

import { useAssistant, useVoiceAssistant } from '../../core/voice/hooks';
import { cn } from '../../lib/cn';
import { THEMES, useUi } from '../../state/uiStore';
import { type Command, rankCommands } from './commands';

/** Shown while typing free text: Enter asks Jarvis. */
const ASK_ID = '__ask__';

/**
 * Ctrl/⌘ + K: jump to any action, or type a question and press Enter to ask
 * Jarvis.
 */
export function CommandPalette() {
  const assistant = useVoiceAssistant();
  const ui = useUi();
  const micActive = useAssistant((s) => s.micActive);
  const soundsEnabled = useAssistant((s) => s.soundsEnabled);
  const voiceId = useAssistant((s) => s.capabilities?.speaker_verification_enabled ?? false);
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const open = ui.overlay === 'palette';

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        if (useUi.getState().overlay === 'palette') useUi.getState().close();
        else useUi.getState().open('palette');
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  useEffect(() => {
    if (!open) return;
    setQuery('');
    setSelected(0);
    requestAnimationFrame(() => inputRef.current?.focus());
  }, [open]);

  const commands = useMemo<Command[]>(() => {
    const close = ui.close;
    const list: Command[] = [
      {
        id: 'briefing',
        title: 'Morning briefing',
        hint: 'Weather, calendar, tasks and headlines',
        keywords: 'brief day summary',
        run: () => assistant.ask('Give me my briefing.'),
      },
      {
        id: 'listen',
        title: 'Talk to Jarvis',
        hint: 'Ctrl+Space',
        keywords: 'push to talk listen',
        run: () => assistant.listen(),
      },
      {
        id: 'edit',
        title: ui.editing ? 'Finish editing layout' : 'Edit layout',
        keywords: 'widgets arrange move resize',
        run: () => ui.setEditing(!ui.editing),
      },
      {
        id: 'add',
        title: 'Add widget…',
        keywords: 'gallery new',
        run: () => {
          ui.setEditing(true);
          ui.open('gallery');
        },
      },
      {
        id: 'settings',
        title: 'Settings…',
        keywords: 'preferences voice persona model',
        run: () => ui.open('settings'),
      },
      {
        id: 'focus',
        title: ui.focus ? 'Leave focus mode' : 'Focus mode',
        hint: 'Hide widgets, quiet chimes',
        keywords: 'minimal distraction',
        run: () => ui.setFocus(!ui.focus),
      },
      {
        id: 'ambient',
        title: 'Ambient mode',
        hint: 'Screensaver clock',
        keywords: 'screensaver idle clock',
        run: () => ui.setAmbient(true),
      },
      {
        id: 'mic',
        title: micActive ? 'Mute microphone' : 'Unmute microphone',
        keywords: 'mic audio',
        run: () => (micActive ? assistant.disableMicrophone() : void assistant.enableMicrophone()),
      },
      {
        id: 'sounds',
        title: soundsEnabled ? 'Mute interface sounds' : 'Enable interface sounds',
        keywords: 'earcons chimes audio',
        run: () => assistant.setSoundsEnabled(!soundsEnabled),
      },
      ...THEMES.map((theme) => ({
        id: `theme-${theme.id}`,
        title: `Theme: ${theme.label}`,
        hint: theme.description,
        keywords: 'appearance colour color',
        run: () => ui.setTheme(theme.id),
      })),
    ];
    if (voiceId) {
      list.push({
        id: 'voice-id',
        title: 'Train voice ID',
        keywords: 'enroll speaker voiceprint',
        run: () => assistant.enrollVoice(),
      });
    }
    return list.map((c) => ({
      ...c,
      run: () => {
        close();
        c.run();
      },
    }));
  }, [assistant, ui, micActive, soundsEnabled, voiceId]);

  const results = rankCommands(commands, query);
  const askEntry: Command | null = query.trim()
    ? {
        id: ASK_ID,
        title: `Ask Jarvis: “${query.trim()}”`,
        run: () => {
          ui.close();
          assistant.ask(query);
        },
      }
    : null;
  const entries =
    askEntry && results.length === 0 ? [askEntry] : askEntry ? [...results, askEntry] : results;
  const active = Math.min(selected, Math.max(0, entries.length - 1));

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          key="palette"
          className="fixed inset-0 z-50 flex items-start justify-center bg-void/55 pt-[14vh] backdrop-blur-md"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) ui.close();
          }}
        >
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label="Command palette"
            initial={{ y: -8, opacity: 0, scale: 0.98 }}
            animate={{ y: 0, opacity: 1, scale: 1 }}
            exit={{ y: -6, opacity: 0 }}
            transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
            className="glass w-[min(92vw,38rem)] overflow-hidden"
          >
            <div className="flex items-center gap-3 border-b border-white/5 px-5">
              <Search className="size-4 text-white/35" />
              <input
                ref={inputRef}
                value={query}
                onChange={(event) => {
                  setQuery(event.target.value);
                  setSelected(0);
                }}
                onKeyDown={(event) => {
                  if (event.key === 'ArrowDown') {
                    event.preventDefault();
                    setSelected((i) => Math.min(i + 1, entries.length - 1));
                  } else if (event.key === 'ArrowUp') {
                    event.preventDefault();
                    setSelected((i) => Math.max(i - 1, 0));
                  } else if (event.key === 'Enter') {
                    event.preventDefault();
                    entries[active]?.run();
                  } else if (event.key === 'Escape') {
                    event.preventDefault();
                    ui.close();
                  }
                }}
                placeholder="Type a command, or ask Jarvis anything…"
                aria-label="Command or question"
                className="h-14 flex-1 bg-transparent text-[15px] text-white/90 placeholder:text-white/30 focus:outline-none"
              />
              <kbd className="font-mono text-[10px] text-white/25">Esc</kbd>
            </div>
            <ul className="hud-scroll max-h-[50vh] overflow-y-auto p-2" role="listbox">
              {entries.map((entry, index) => (
                <li key={entry.id} role="option" aria-selected={index === active}>
                  <button
                    type="button"
                    onMouseEnter={() => setSelected(index)}
                    onClick={() => entry.run()}
                    className={cn(
                      'flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition',
                      index === active ? 'bg-white/[0.06]' : 'hover:bg-white/[0.03]',
                    )}
                  >
                    {entry.id === ASK_ID && <MessageSquare className="size-4 text-arc-300" />}
                    <span className="flex-1">
                      <span className="block text-[13.5px] text-white/90">{entry.title}</span>
                      {entry.hint && (
                        <span className="block text-[12px] text-white/35">{entry.hint}</span>
                      )}
                    </span>
                    {index === active && <CornerDownLeft className="size-3.5 text-white/30" />}
                  </button>
                </li>
              ))}
            </ul>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
