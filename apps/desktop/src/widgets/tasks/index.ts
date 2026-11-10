import { defineWidget } from '@jarvis/widget-sdk';

import { TasksWidget } from './TasksWidget';

/**
 * Backed by the core service today (`/api/tasks`, `/api/reminders`). When the
 * Tasks mobile app ships it will sync with the same API, so this widget
 * doesn't change.
 */
export default defineWidget({
  manifest: {
    id: 'tasks',
    name: 'Tasks',
    description: 'Open tasks and upcoming reminders — editable by voice or by hand.',
    version: '1.0.0',
    defaultSize: { cols: 2, rows: 3 },
    minRows: 2,
    source: { kind: 'builtin' },
    permissions: ['network', 'voice-intents'],
    voiceIntents: ['tasks.add', 'tasks.list', 'tasks.complete', 'reminders.add'],
  },
  component: TasksWidget,
});
