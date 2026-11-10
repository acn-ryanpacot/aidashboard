import { defineWidget } from '@jarvis/widget-sdk';

import { ScheduleWidget } from './ScheduleWidget';

/**
 * Reads any ICS calendar (Google, Outlook, Apple, files). When the Schedule
 * mobile app ships, it can publish its own ICS feed or sync via the core API.
 */
export default defineWidget({
  manifest: {
    id: 'schedule',
    name: 'Schedule',
    description: 'Today’s and tomorrow’s events from your calendars.',
    version: '1.0.0',
    defaultSize: { cols: 2, rows: 3 },
    minRows: 2,
    source: { kind: 'builtin' },
    permissions: ['network', 'voice-intents'],
    voiceIntents: ['schedule.list'],
  },
  component: ScheduleWidget,
});
