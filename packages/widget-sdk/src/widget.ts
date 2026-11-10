/**
 * Runtime widget definitions and the registry the dashboard renders from.
 *
 * @module
 */
import type { ComponentType } from 'react';

import { type WidgetManifest, type WidgetSize, validateManifest } from './manifest';

/** Props the dashboard passes to every widget component. */
export interface WidgetProps {
  /** The footprint the widget is currently rendered at. */
  readonly size: WidgetSize;
}

/** A manifest paired with the React component that renders it. */
export interface WidgetDefinition {
  readonly manifest: WidgetManifest;
  readonly component: ComponentType<WidgetProps>;
}

/** Thrown when a widget definition is invalid or conflicts with another. */
export class WidgetDefinitionError extends Error {
  override readonly name = 'WidgetDefinitionError';
}

/**
 * Declare a widget. Validates the manifest eagerly so mistakes surface at
 * import time rather than as a broken tile.
 *
 * @throws {@link WidgetDefinitionError} if the manifest is invalid.
 *
 * @example
 * ```tsx
 * export default defineWidget({
 *   manifest: { id: 'clock', name: 'Clock', ... },
 *   component: ClockWidget,
 * });
 * ```
 */
export function defineWidget(definition: WidgetDefinition): WidgetDefinition {
  const problems = validateManifest(definition.manifest);
  if (problems.length > 0) {
    throw new WidgetDefinitionError(
      `Invalid widget "${definition.manifest.id}": ${problems.join('; ')}`,
    );
  }
  return Object.freeze({ ...definition, manifest: Object.freeze({ ...definition.manifest }) });
}

/**
 * An in-memory catalogue of available widgets, keyed by manifest id.
 *
 * The dashboard asks the registry what it can render; the user's layout (a
 * separate concern) decides where each widget goes.
 */
export class WidgetRegistry {
  readonly #widgets = new Map<string, WidgetDefinition>();

  /**
   * Add a widget.
   *
   * @throws {@link WidgetDefinitionError} if a widget with the same id exists.
   */
  register(definition: WidgetDefinition): this {
    const { id } = definition.manifest;
    if (this.#widgets.has(id)) {
      throw new WidgetDefinitionError(`A widget with id "${id}" is already registered`);
    }
    this.#widgets.set(id, definition);
    return this;
  }

  /** Look up a widget by id. */
  get(id: string): WidgetDefinition | undefined {
    return this.#widgets.get(id);
  }

  /** All registered widgets, in registration order. */
  list(): WidgetDefinition[] {
    return [...this.#widgets.values()];
  }
}
