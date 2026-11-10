import { defineWidget } from '@jarvis/widget-sdk';

import { CoreLinkWidget } from './CoreLinkWidget';

export default defineWidget({
  manifest: {
    id: 'core-link',
    name: 'Systems',
    description: 'Subsystem status, voice ID and last-turn latency.',
    version: '1.0.0',
    defaultSize: { cols: 2, rows: 3 },
    minRows: 3,
    source: { kind: 'builtin' },
  },
  component: CoreLinkWidget,
});
