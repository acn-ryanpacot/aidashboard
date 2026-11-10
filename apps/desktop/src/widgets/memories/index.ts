import { defineWidget } from '@jarvis/widget-sdk';

import { MemoriesWidget } from './MemoriesWidget';

export default defineWidget({
  manifest: {
    id: 'memories',
    name: 'Memory',
    description: 'Facts Jarvis remembers about you; hover one to forget it.',
    version: '1.0.0',
    defaultSize: { cols: 2, rows: 3 },
    minRows: 2,
    source: { kind: 'builtin' },
    permissions: ['storage', 'voice-intents'],
    voiceIntents: ['memory.remember', 'memory.forget'],
  },
  component: MemoriesWidget,
});
