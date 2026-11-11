import { defineWidget } from '@jarvis/widget-sdk';

import { TimersWidget } from './TimersWidget';

export default defineWidget({
  manifest: {
    id: 'timers',
    name: 'Timers',
    description: 'Countdown timers with a ring; Jarvis says when each is done.',
    version: '1.0.0',
    defaultSize: { cols: 2, rows: 2 },
    minRows: 2,
    source: { kind: 'builtin' },
    permissions: ['storage', 'voice-intents', 'notifications'],
    voiceIntents: ['timers.start', 'timers.cancel'],
  },
  component: TimersWidget,
});
