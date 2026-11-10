/**
 * The widget manifest: static, serialisable metadata describing a widget.
 *
 * Manifests are deliberately plain JSON so that a future mobile app can ship
 * one over the network and the dashboard can render a tile for it without
 * new desktop code.
 *
 * @module
 */

/** Grid footprint, in dashboard cells. */
export interface WidgetSize {
  /** Columns spanned within a dashboard zone (1–2). */
  readonly cols: 1 | 2;
  /** Rows spanned (1 row ≈ 96 px). */
  readonly rows: 1 | 2 | 3 | 4;
}

/**
 * Capabilities a widget may request. The host will enforce these once
 * third-party widgets are supported (Phase 6).
 */
export type WidgetPermission =
  'network' | 'notifications' | 'voice-intents' | 'storage' | 'location';

/** Where a widget's data comes from. */
export type WidgetSource =
  | { readonly kind: 'builtin' }
  | {
      readonly kind: 'mobile-app';
      /** Identifier of the companion mobile app, e.g. `com.ryan.tasks`. */
      readonly appId: string;
      /** Core-service route that proxies the app's data, e.g. `/api/apps/tasks`. */
      readonly endpoint: string;
    };

/** Static description of a widget. */
export interface WidgetManifest {
  /** Globally unique, kebab-case id, e.g. `clock` or `tasks-today`. */
  readonly id: string;
  /** Human-readable title shown in the tile header. */
  readonly name: string;
  /** One-sentence summary (shown in the future widget gallery). */
  readonly description: string;
  /** Semantic version of the widget, e.g. `1.0.0`. */
  readonly version: string;
  /** Default footprint. */
  readonly defaultSize: WidgetSize;
  /** Smallest height (rows) at which the widget still reads well. Defaults to 1. */
  readonly minRows?: WidgetSize['rows'];
  /** Data origin. */
  readonly source: WidgetSource;
  /** Requested capabilities. */
  readonly permissions?: readonly WidgetPermission[];
  /**
   * Voice intents this widget can fulfil, e.g. `tasks.add`. The AI layer
   * routes matching requests to the widget's backend tools (Phase 3).
   */
  readonly voiceIntents?: readonly string[];
}

const ID_PATTERN = /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/;
const SEMVER_PATTERN = /^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$/;
const INTENT_PATTERN = /^[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)+$/;

/**
 * Check a manifest for structural problems.
 *
 * @param manifest - The manifest to validate.
 * @returns A list of human-readable problems; empty when the manifest is valid.
 *
 * @example
 * ```ts
 * validateManifest({ ...manifest, id: 'Bad Id' });
 * // → ['id "Bad Id" must be kebab-case']
 * ```
 */
export function validateManifest(manifest: WidgetManifest): string[] {
  const problems: string[] = [];
  if (!ID_PATTERN.test(manifest.id)) problems.push(`id "${manifest.id}" must be kebab-case`);
  if (!manifest.name.trim()) problems.push('name must not be empty');
  if (!SEMVER_PATTERN.test(manifest.version)) {
    problems.push(`version "${manifest.version}" must be semver (e.g. 1.0.0)`);
  }
  const { cols, rows } = manifest.defaultSize;
  if (![1, 2].includes(cols)) problems.push(`defaultSize.cols must be 1 or 2, got ${cols}`);
  if (![1, 2, 3, 4].includes(rows)) problems.push(`defaultSize.rows must be 1–4, got ${rows}`);
  if (manifest.minRows !== undefined && manifest.minRows > rows) {
    problems.push(`minRows (${manifest.minRows}) must not exceed defaultSize.rows (${rows})`);
  }
  if (manifest.source.kind === 'mobile-app') {
    if (!manifest.source.appId.trim()) problems.push('source.appId must not be empty');
    if (!manifest.source.endpoint.startsWith('/api/')) {
      problems.push('source.endpoint must be a core-service route starting with /api/');
    }
  }
  for (const intent of manifest.voiceIntents ?? []) {
    if (!INTENT_PATTERN.test(intent)) {
      problems.push(`voice intent "${intent}" must look like "domain.action"`);
    }
  }
  return problems;
}
