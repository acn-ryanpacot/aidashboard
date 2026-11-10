import { ArrowUp, Square } from 'lucide-react';
import { type FormEvent, useEffect, useRef, useState } from 'react';

import { useAssistant, useVoiceAssistant } from '../../core/voice/hooks';
import { cn } from '../../lib/cn';

/**
 * Text input for typed questions. `Ctrl/⌘ + K` focuses it; `Esc` stops Jarvis.
 */
export function CommandBar() {
  const assistant = useVoiceAssistant();
  const state = useAssistant((s) => s.state);
  const online = useAssistant((s) => s.connection === 'online');
  const [text, setText] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const busy = state === 'thinking' || state === 'speaking';

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        inputRef.current?.focus();
      } else if (event.key === 'Escape') {
        assistant.cancel();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [assistant]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!text.trim()) return;
    assistant.ask(text);
    setText('');
  };

  return (
    <form
      onSubmit={submit}
      className="glass group flex w-full max-w-2xl items-center gap-3 py-2 pr-2 pl-5"
    >
      <input
        ref={inputRef}
        value={text}
        onChange={(event) => setText(event.target.value)}
        placeholder={online ? 'Ask Jarvis anything…' : 'Waiting for the core service…'}
        disabled={!online}
        className="h-10 flex-1 bg-transparent text-[15px] text-white/90 placeholder:text-white/30 focus:outline-none disabled:cursor-not-allowed"
        aria-label="Ask Jarvis"
      />
      <kbd className="hidden font-mono text-[10px] text-white/25 sm:block">Ctrl K</kbd>
      {busy ? (
        <button
          type="button"
          onClick={() => assistant.cancel()}
          className="flex size-10 items-center justify-center rounded-xl bg-white/5 text-white/70 transition hover:bg-white/10"
          aria-label="Stop"
          title="Stop (Esc)"
        >
          <Square className="size-3.5 fill-current" />
        </button>
      ) : (
        <button
          type="submit"
          disabled={!online || !text.trim()}
          className={cn(
            'flex size-10 items-center justify-center rounded-xl transition',
            'bg-arc-400/90 text-void hover:bg-arc-300 disabled:bg-white/5 disabled:text-white/25',
          )}
          aria-label="Send"
        >
          <ArrowUp className="size-4" strokeWidth={2.5} />
        </button>
      )}
    </form>
  );
}
