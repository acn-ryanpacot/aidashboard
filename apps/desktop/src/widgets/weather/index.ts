import { defineWidget } from '@jarvis/widget-sdk';

import { WeatherWidget } from './WeatherWidget';

export default defineWidget({
  manifest: {
    id: 'weather',
    name: 'Weather',
    description: 'Current conditions and today’s high and low (Open-Meteo, free).',
    version: '1.0.0',
    defaultSize: { cols: 2, rows: 2 },
    minRows: 2,
    source: { kind: 'builtin' },
    permissions: ['network', 'location'],
    voiceIntents: ['weather.current'],
  },
  component: WeatherWidget,
});
