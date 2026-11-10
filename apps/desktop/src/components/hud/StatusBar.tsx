import { Mic, MicOff } from 'lucide-react';

import { APP_VERSION } from '../../config';
import { useAssistant, useVoiceAssistant } from '../../core/voice/hooks';
import { cn } from '../../lib/cn';
import { StatusDot, type Tone } from '../ui/StatusDot';

const CONNECTION: Record<string, { tone: Tone; label: string }> = {
  connecting: { tone: 'warn', label: 'Linking core' },
  online: { tone: 'ok', label: 'Core online' },
  offline: { tone: 'error', label: 'Core offline' },
};

/** Top bar: wordmark, link status and microphone toggle. */
export function StatusBar() {
  const assistant = useVoiceAssistant();
  const connection = useAssistant((s) => s.connection);
  const micActive = useAssistant((s) => s.micActive);
  const engaged = useAssistant((s) => s.engaged);
  const link = CONNECTION[connection] ?? { tone: 'muted' as Tone, label: connection };

  return (
    <header className="relative z-10 flex h-16 items-center justify-between px-8">
      <div className="flex items-baseline gap-3">
        <span className="text-[13px] font-semibold tracking-[0.55em] text-white/90">JARVIS</span>
        <span className="font-mono text-[10px] tracking-[0.3em] text-arc-300/70">OS</span>
        <span className="font-mono text-[10px] text-white/25">v{APP_VERSION}</span>
      </div>

      <div className="flex items-center gap-3">
        <div className="glass-pill flex items-center gap-2.5 px-3.5 py-1.5">
          <StatusDot tone={link.tone} />
          <span className="font-mono text-[10px] tracking-[0.22em] text-white/60 uppercase">
            {link.label}
          </span>
        </div>
        <button
          type="button"
          disabled={!engaged}
          onClick={() =>
            micActive ? assistant.disableMicrophone() : void assistant.enableMicrophone()
          }
          className={cn(
            'glass-pill flex size-9 items-center justify-center transition-colors',
            micActive ? 'text-arc-300 hover:text-arc-200' : 'text-white/40 hover:text-white/70',
            'disabled:cursor-not-allowed disabled:opacity-40',
          )}
          aria-label={micActive ? 'Mute microphone' : 'Unmute microphone'}
          title={micActive ? 'Mute microphone' : 'Unmute microphone'}
        >
          {micActive ? <Mic className="size-4" /> : <MicOff className="size-4" />}
        </button>
      </div>
    </header>
  );
}
