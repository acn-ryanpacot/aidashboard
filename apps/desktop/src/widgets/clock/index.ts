import { defineWidget } from '@jarvis/widget-sdk';

import { ClockWidget } from './ClockWidget';

export default defineWidget({
  manifest: {
    id: 'clock',
    name: 'Chronometer',
    description: 'Local time, date and a greeting.',
    version: '1.0.0',
    defaultSize: { cols: 2, rows: 2 },
    source: { kind: 'builtin' },
  },
  component: ClockWidget,
});
