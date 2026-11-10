import { createContext } from 'react';

import type { VoiceAssistant } from './VoiceAssistant';

/** React context carrying the app's single {@link VoiceAssistant}. */
export const VoiceAssistantContext = createContext<VoiceAssistant | null>(null);
