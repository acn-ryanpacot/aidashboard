/**
 * Jarvis OS widget SDK.
 *
 * A widget = a {@link WidgetManifest} (what it is) + a React component (how it
 * looks). Register widgets with a {@link WidgetRegistry}; the dashboard's
 * layout decides where they appear.
 *
 * @packageDocumentation
 */
export type { WidgetManifest, WidgetPermission, WidgetSize, WidgetSource } from './manifest';
export { validateManifest } from './manifest';
export type { WidgetDefinition, WidgetProps } from './widget';
export { WidgetDefinitionError, WidgetRegistry, defineWidget } from './widget';
