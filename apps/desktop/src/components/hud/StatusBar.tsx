import {
  Bell,
  Command,
  Focus,
  LayoutDashboard,
  Mic,
  MicOff,
  Settings,
  Volume2,
  VolumeX,
} from 'lucide-react';

import { APP_VERSION } from '../../config';
import { coreApi } from '../../core/api/client';
import { useCoreData } from '../../core/api/useCoreData';
import { useAssistant, useVoiceAssistant } from '../../core/voice/hooks';
import { cn } from '../../lib/cn';
import { useUi } from '../../state/uiStore';
import { StatusDot, type Tone } from '../ui/StatusDot';

const CONNECTION: Record<string, { tone: Tone; label: string }> = {
  connecting: { tone: 'warn', label: 'Linking core' },
  online: { tone: 'ok', label: 'Core online' },
  offline: { tone: 'error', label: 'Core offline' },
};

const ICON_BUTTON = cn(
  'glass-pill flex size-9 items-center justify-center transition-colors',
  'disabled:cursor-not-allowed disabled:opacity-40',
);

/** Top bar: wordmark, link status, layout/focus/settings and audio toggles. */
export function StatusBar() {
  const assistant = useVoiceAssistant();
  const connection = useAssistant((s) => s.connection);
  const micActive = useAssistant((s) => s.micActive);
  const engaged = useAssistant((s) => s.engaged);
  const soundsEnabled = useAssistant((s) => s.soundsEnabled);
  const link = CONNECTION[connection] ?? { tone: 'muted' as Tone, label: connection };
  const ui = useUi();
  const unread = useCoreData(['notifications'], coreApi.listNotifications).data?.unread ?? 0;

  return (
    <header className="relative z-10 flex h-16 shrink-0 items-center justify-between px-4 sm:px-8">
      <div className="flex items-baseline gap-3">
        <span className="text-[13px] font-semibold tracking-[0.55em] text-white/90">JARVIS</span>
        <span className="font-mono text-[10px] tracking-[0.3em] text-arc-300/70">OS</span>
        <span className="hidden font-mono text-[10px] text-white/25 sm:inline">v{APP_VERSION}</span>
      </div>

      <div className="flex items-center gap-2 sm:gap-3">
        <div
          className="glass-pill flex items-center gap-2.5 px-3 py-1.5 sm:px-3.5"
          title={link.label}
        >
          <StatusDot tone={link.tone} />
          <span className="hidden font-mono text-[10px] tracking-[0.22em] text-white/60 uppercase sm:inline">
            {link.label}
          </span>
        </div>
        {/* Keyboard palette and layout editing are desktop affordances. */}
        <button
          type="button"
          onClick={() => ui.open('palette')}
          className={cn(
            ICON_BUTTON,
            'hidden w-auto gap-2 px-3 text-white/45 hover:text-white/80 xl:flex',
          )}
          aria-label="Open command palette"
          title="Command palette (Ctrl+K)"
        >
          <Command className="size-3.5" />
          <span className="font-mono text-[10px]">K</span>
        </button>
        <button
          type="button"
          onClick={() => ui.setEditing(!ui.editing)}
          aria-pressed={ui.editing}
          className={cn(
            ICON_BUTTON,
            'hidden xl:flex',
            ui.editing ? 'text-arc-300' : 'text-white/45 hover:text-white/80',
          )}
          aria-label={ui.editing ? 'Finish editing layout' : 'Edit layout'}
          title={ui.editing ? 'Finish editing layout' : 'Edit layout'}
        >
          <LayoutDashboard className="size-4" />
        </button>
        <button
          type="button"
          onClick={() => ui.setFocus(!ui.focus)}
          aria-pressed={ui.focus}
          className={cn(
            ICON_BUTTON,
            ui.focus ? 'text-arc-300' : 'text-white/45 hover:text-white/80',
          )}
          aria-label={ui.focus ? 'Leave focus mode' : 'Focus mode'}
          title={ui.focus ? 'Leave focus mode' : 'Focus mode: hide widgets, quiet chimes'}
        >
          <Focus className="size-4" />
        </button>
        <button
          type="button"
          onClick={() => ui.open('notifications')}
          className={cn(ICON_BUTTON, 'relative text-white/45 hover:text-white/80')}
          aria-label={unread ? `Notifications (${unread} unread)` : 'Notifications'}
          title="Notifications"
        >
          <Bell className="size-4" />
          {unread > 0 && (
            <span className="absolute -top-1 -right-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-arc-400 px-1 font-mono text-[9px] font-semibold text-void">
              {unread > 99 ? '99+' : unread}
            </span>
          )}
        </button>
        <button
          type="button"
          onClick={() => ui.open('settings')}
          className={cn(ICON_BUTTON, 'text-white/45 hover:text-white/80')}
          aria-label="Settings"
          title="Settings"
        >
          <Settings className="size-4" />
        </button>
        <button
          type="button"
          onClick={() => assistant.setSoundsEnabled(!soundsEnabled)}
          className={cn(
            ICON_BUTTON,
            soundsEnabled
              ? 'text-white/60 hover:text-white/85'
              : 'text-white/30 hover:text-white/60',
          )}
          aria-label={soundsEnabled ? 'Mute interface sounds' : 'Enable interface sounds'}
          title={soundsEnabled ? 'Mute interface sounds' : 'Enable interface sounds'}
        >
          {soundsEnabled ? <Volume2 className="size-4" /> : <VolumeX className="size-4" />}
        </button>
        <button
          type="button"
          disabled={!engaged}
          onClick={() =>
            micActive ? assistant.disableMicrophone() : void assistant.enableMicrophone()
          }
          className={cn(
            ICON_BUTTON,
            micActive ? 'text-arc-300 hover:text-arc-200' : 'text-white/40 hover:text-white/70',
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
