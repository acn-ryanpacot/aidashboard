/**
 * The catalogue of widgets available to the dashboard.
 *
 * To add a widget: create it with `defineWidget` (see `src/widgets/*`) and
 * register it here; then place its id in {@link ./layout.ts}.
 *
 * @module
 */
import { WidgetRegistry } from '@jarvis/widget-sdk';

import clock from '../widgets/clock';
import conversation from '../widgets/conversation';
import coreLink from '../widgets/core-link';
import { createAppPlaceholder } from '../widgets/placeholders/createAppPlaceholder';
import tasks from '../widgets/tasks';

export const widgetRegistry = new WidgetRegistry()
  .register(clock)
  .register(coreLink)
  .register(conversation)
  .register(
    createAppPlaceholder({
      id: 'schedule',
      name: 'Schedule',
      description: "Today's events from the Schedule app.",
      appId: 'schedule',
      intents: ['schedule.list', 'schedule.add'],
    }),
  )
  .register(tasks)
  .register(
    createAppPlaceholder({
      id: 'news',
      name: 'Briefing',
      description: 'Headlines curated by the News app.',
      appId: 'news',
      intents: ['news.headlines'],
    }),
  );
