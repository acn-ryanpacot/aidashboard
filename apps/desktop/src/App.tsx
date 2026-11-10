import { motion } from 'motion/react';

import { Captions } from './components/hud/Captions';
import { CommandBar } from './components/hud/CommandBar';
import { EngageOverlay } from './components/hud/EngageOverlay';
import { EnrollmentOverlay } from './components/hud/EnrollmentOverlay';
import { Orb } from './components/hud/Orb';
import { StatusBar } from './components/hud/StatusBar';
import { VOICE_WS_URL } from './config';
import { usePushToTalk } from './core/voice/usePushToTalk';
import { VoiceAssistantProvider } from './core/voice/VoiceAssistantProvider';
import { DashboardZone } from './dashboard/DashboardZone';

/** Root: provides the voice assistant to the HUD. */
export function App() {
  return (
    <VoiceAssistantProvider url={VOICE_WS_URL}>
      <Hud />
    </VoiceAssistantProvider>
  );
}

/** Layout: status bar, two widget zones and the central voice core. */
function Hud() {
  usePushToTalk();
  return (
    <>
      <div className="hud-backdrop" aria-hidden />
      <div className="relative flex h-screen flex-col overflow-hidden">
        <StatusBar />
        <main className="grid min-h-0 flex-1 grid-cols-1 gap-6 px-8 pb-8 xl:grid-cols-[minmax(300px,340px)_1fr_minmax(320px,380px)]">
          <DashboardZone zone="left" className="hidden xl:flex" />

          <motion.section
            initial={{ opacity: 0, scale: 0.97 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 1, ease: [0.22, 1, 0.36, 1] }}
            className="flex min-h-0 flex-col items-center justify-center gap-6"
          >
            <Orb />
            <Captions />
            <CommandBar />
          </motion.section>

          <DashboardZone zone="right" className="hidden xl:flex" />
        </main>
      </div>
      <EngageOverlay />
      <EnrollmentOverlay />
    </>
  );
}
