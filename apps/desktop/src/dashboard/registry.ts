/**
 * The catalogue of widgets available to the dashboard.
 *
 * To add a widget: create it with `defineWidget` (see `src/widgets/*`) and
 * register it here. It then appears in the "Add widget" gallery; add it to
 * `DEFAULT_LAYOUT` (state/layout.ts) to show it out of the box.
 *
 * @module
 */
import { WidgetRegistry } from '@jarvis/widget-sdk';

import clock from '../widgets/clock';
import conversation from '../widgets/conversation';
import coreLink from '../widgets/core-link';
import memories from '../widgets/memories';
import news from '../widgets/news';
import portfolio from '../widgets/portfolio';
import schedule from '../widgets/schedule';
import system from '../widgets/system';
import tasks from '../widgets/tasks';
import timers from '../widgets/timers';
import weather from '../widgets/weather';

export const widgetRegistry = new WidgetRegistry()
  .register(clock)
  .register(weather)
  .register(schedule)
  .register(conversation)
  .register(tasks)
  .register(timers)
  .register(news)
  .register(portfolio)
  .register(memories)
  .register(system)
  .register(coreLink);

/** Ids of every registered widget (used to sanitise stored layouts). */
export const KNOWN_WIDGET_IDS: ReadonlySet<string> = new Set(
  widgetRegistry.list().map((w) => w.manifest.id),
);
