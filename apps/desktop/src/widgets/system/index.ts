import { defineWidget } from '@jarvis/widget-sdk';

import { SystemWidget } from './SystemWidget';

export default defineWidget({
  manifest: {
    id: 'system',
    name: 'Machine',
    description: 'CPU, memory and GPU load (VRAM shows how much room your models use).',
    version: '1.0.0',
    defaultSize: { cols: 2, rows: 2 },
    minRows: 2,
    source: { kind: 'builtin' },
  },
  component: SystemWidget,
});
