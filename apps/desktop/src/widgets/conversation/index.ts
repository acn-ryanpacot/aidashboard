import { defineWidget } from '@jarvis/widget-sdk';

import { ConversationWidget } from './ConversationWidget';

export default defineWidget({
  manifest: {
    id: 'conversation',
    name: 'Conversation',
    description: 'Transcript of what you and Jarvis have said this session.',
    version: '1.0.0',
    defaultSize: { cols: 2, rows: 4 },
    minRows: 2,
    source: { kind: 'builtin' },
  },
  component: ConversationWidget,
});
