import { AnimatePresence, motion } from 'motion/react';
import { useEffect } from 'react';

import { AmbientScreen } from './components/hud/AmbientScreen';
import { Captions } from './components/hud/Captions';
import { CommandBar } from './components/hud/CommandBar';
import { CommandPalette } from './components/hud/CommandPalette';
import { EngageOverlay } from './components/hud/EngageOverlay';
import { EnrollmentOverlay } from './components/hud/EnrollmentOverlay';
import { Orb } from './components/hud/Orb';
import { PairingScreen } from './components/hud/PairingScreen';
import { StatusBar } from './components/hud/StatusBar';
import { useAmbientMode } from './components/hud/useAmbientMode';
import { SettingsPanel } from './components/settings/SettingsPanel';
import { VOICE_WS_URL } from './config';
import { useVoiceAssistant } from './core/voice/hooks';
import { usePushToTalk } from './core/voice/usePushToTalk';
import { VoiceAssistantProvider } from './core/voice/VoiceAssistantProvider';
import { DashboardZone } from './dashboard/DashboardZone';
import { useLayoutSync } from './dashboard/useLayoutSync';
import { WidgetGallery } from './dashboard/WidgetGallery';
import { cn } from './lib/cn';
import { useUi } from './state/uiStore';

/** Root: provides the voice assistant to the HUD. */
export function App() {
  return (
    <VoiceAssistantProvider url={VOICE_WS_URL}>
      <Hud />
    </VoiceAssistantProvider>
  );
}

/** Applies the theme and keeps the voice controller in step with focus mode. */
function useAppearance(): void {
  const theme = useUi((s) => s.theme);
  const focus = useUi((s) => s.focus);
  const assistant = useVoiceAssistant();

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  useEffect(() => {
    assistant.setQuietNotifications(focus);
  }, [assistant, focus]);
}

/** Layout: status bar, two widget zones and the central voice core. */
function Hud() {
  usePushToTalk();
  useLayoutSync();
  useAmbientMode();
  useAppearance();
  const focus = useUi((s) => s.focus);
  const editing = useUi((s) => s.editing);

  return (
    <>
      <div className="hud-backdrop" aria-hidden />
      <div className="relative flex h-screen flex-col overflow-hidden">
        <StatusBar />
        {editing && (
          <p className="pointer-events-none absolute top-16 left-1/2 z-10 -translate-x-1/2 font-mono text-[10px] tracking-[0.3em] text-arc-300/70 uppercase">
            Editing layout · drag tiles · ± to resize
          </p>
        )}
        {/*
          Desktop (xl+): three columns that fit the window. Phone and tablet: one
          scrolling column with the core first, then the widgets stacked below.
        */}
        <main
          className={cn(
            'hud-scroll flex min-h-0 flex-1 flex-col gap-6 overflow-y-auto px-4 pb-8 sm:px-8',
            'xl:grid xl:grid-cols-1 xl:overflow-visible',
            !focus && 'xl:grid-cols-[minmax(300px,340px)_1fr_minmax(320px,380px)]',
          )}
        >
          <AnimatePresence initial={false}>
            {!focus && (
              <motion.div
                key="left"
                className="order-2 flex min-h-0 shrink-0 xl:order-none"
                initial={{ opacity: 0, x: -12 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -12 }}
              >
                <DashboardZone zone="left" className="flex-1" />
              </motion.div>
            )}
          </AnimatePresence>

          <motion.section
            initial={{ opacity: 0, scale: 0.97 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 1, ease: [0.22, 1, 0.36, 1] }}
            className="order-1 flex shrink-0 flex-col items-center justify-center gap-6 xl:order-none xl:min-h-0 xl:shrink"
          >
            <Orb />
            <Captions />
            <CommandBar />
          </motion.section>

          <AnimatePresence initial={false}>
            {!focus && (
              <motion.div
                key="right"
                className="order-3 flex min-h-0 shrink-0 xl:order-none"
                initial={{ opacity: 0, x: 12 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 12 }}
              >
                <DashboardZone zone="right" className="flex-1" />
              </motion.div>
            )}
          </AnimatePresence>
        </main>
      </div>
      <AmbientScreen />
      <CommandPalette />
      <SettingsPanel />
      <WidgetGallery />
      <EngageOverlay />
      <EnrollmentOverlay />
      <PairingScreen />
    </>
  );
}
