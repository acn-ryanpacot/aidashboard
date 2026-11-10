import { defineWidget } from '@jarvis/widget-sdk';

import { NewsWidget } from './NewsWidget';

/**
 * Headlines from RSS/Atom feeds. When the News mobile app ships, it can expose
 * curated feeds through the same `/api/news` endpoint.
 */
export default defineWidget({
  manifest: {
    id: 'news',
    name: 'Briefing',
    description: 'Latest headlines from your RSS/Atom feeds.',
    version: '1.0.0',
    defaultSize: { cols: 2, rows: 2 },
    minRows: 2,
    source: { kind: 'builtin' },
    permissions: ['network', 'voice-intents'],
    voiceIntents: ['news.headlines'],
  },
  component: NewsWidget,
});
