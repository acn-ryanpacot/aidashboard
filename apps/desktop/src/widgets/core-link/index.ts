import { defineWidget } from '@jarvis/widget-sdk';

import { CoreLinkWidget } from './CoreLinkWidget';

export default defineWidget({
  manifest: {
    id: 'core-link',
    name: 'Systems',
    description: 'Status of the wake word, speech and microphone subsystems.',
    version: '1.0.0',
    defaultSize: { cols: 2, rows: 2 },
    source: { kind: 'builtin' },
  },
  component: CoreLinkWidget,
});
