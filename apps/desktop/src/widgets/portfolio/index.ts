import { defineWidget } from '@jarvis/widget-sdk';

import { PortfolioWidget } from './PortfolioWidget';

/**
 * Your PSE portfolio from the PisoTiyempo app: the latest session's move and
 * each holding, or (when you hold nothing) three trend-and-value ideas. The
 * core proxies PisoTiyempo's local feed at `/api/apps/pisotiyempo`; see
 * `docs/guides/pisotiyempo.md`.
 */
export default defineWidget({
  manifest: {
    id: 'portfolio',
    name: 'Portfolio',
    description: 'Your PSE stocks from PisoTiyempo, or three trend-and-value ideas.',
    version: '1.0.0',
    defaultSize: { cols: 2, rows: 3 },
    minRows: 2,
    source: { kind: 'mobile-app', appId: 'com.pisotiyempo', endpoint: '/api/apps/pisotiyempo' },
    permissions: ['network', 'voice-intents'],
    voiceIntents: ['stocks.portfolio', 'stocks.ideas'],
  },
  component: PortfolioWidget,
});
