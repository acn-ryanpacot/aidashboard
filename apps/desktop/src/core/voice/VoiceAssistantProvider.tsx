import { type ReactNode, useEffect, useState } from 'react';

import { VoiceAssistantContext } from './context';
import { VoiceAssistant } from './VoiceAssistant';

interface Props {
  /** WebSocket URL of the core service's voice endpoint. */
  readonly url: string;
  readonly children: ReactNode;
}

/** Creates the voice assistant once and keeps it connected while mounted. */
export function VoiceAssistantProvider({ url, children }: Props) {
  const [assistant] = useState(() => new VoiceAssistant(url));

  useEffect(() => {
    assistant.start();
    return () => assistant.dispose();
  }, [assistant]);

  return <VoiceAssistantContext value={assistant}>{children}</VoiceAssistantContext>;
}
