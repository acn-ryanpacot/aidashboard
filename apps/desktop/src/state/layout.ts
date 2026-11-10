/**
 * The user-editable dashboard layout: which widgets sit in which zone, in
 * which order, at which height. Pure reducers, persisted by
 * `useDashboardLayout` to the core service (`/api/ui-preferences/layout`).
 *
 * @module
 */

/** The dashboard's side columns flanking the central core. */
export type DashboardZone = 'left' | 'right';

export const ZONES: readonly DashboardZone[] = ['left', 'right'];

/** Rows a widget can span (one row ≈ 96 px; 4 = fill the remaining height). */
export type Rows = 1 | 2 | 3 | 4;

/** One widget placed on the dashboard. */
export interface Placement {
  readonly id: string;
  readonly rows: Rows;
}

/** The whole layout document. */
export interface DashboardLayout {
  readonly version: 1;
  readonly zones: Readonly<Record<DashboardZone, readonly Placement[]>>;
}

export const DEFAULT_LAYOUT: DashboardLayout = {
  version: 1,
  zones: {
    left: [
      { id: 'clock', rows: 2 },
      { id: 'weather', rows: 2 },
      { id: 'schedule', rows: 3 },
    ],
    right: [
      { id: 'conversation', rows: 4 },
      { id: 'tasks', rows: 3 },
      { id: 'news', rows: 2 },
    ],
  },
};

const clampRows = (rows: number): Rows => Math.min(4, Math.max(1, Math.round(rows))) as Rows;

function mapZones(
  layout: DashboardLayout,
  fn: (placements: readonly Placement[], zone: DashboardZone) => readonly Placement[],
): DashboardLayout {
  return {
    version: 1,
    zones: { left: fn(layout.zones.left, 'left'), right: fn(layout.zones.right, 'right') },
  };
}

/** Every widget id currently on the dashboard. */
export function placedIds(layout: DashboardLayout): Set<string> {
  return new Set(ZONES.flatMap((zone) => layout.zones[zone].map((p) => p.id)));
}

/** Where a widget is, if placed. */
export function findWidget(
  layout: DashboardLayout,
  id: string,
): { zone: DashboardZone; index: number } | null {
  for (const zone of ZONES) {
    const index = layout.zones[zone].findIndex((p) => p.id === id);
    if (index >= 0) return { zone, index };
  }
  return null;
}

/**
 * Move a widget to `zone` at `index` (in the destination's coordinates,
 * computed after removing the widget from its old spot).
 */
export function moveWidget(
  layout: DashboardLayout,
  id: string,
  zone: DashboardZone,
  index: number,
): DashboardLayout {
  const from = findWidget(layout, id);
  if (!from) return layout;
  const placement = layout.zones[from.zone][from.index] as Placement;
  const without = mapZones(layout, (list) => list.filter((p) => p.id !== id));
  return mapZones(without, (list, z) => {
    if (z !== zone) return list;
    const at = Math.max(0, Math.min(index, list.length));
    return [...list.slice(0, at), placement, ...list.slice(at)];
  });
}

/** Grow or shrink a widget by `delta` rows (clamped to 1–4). */
export function resizeWidget(layout: DashboardLayout, id: string, delta: number): DashboardLayout {
  return mapZones(layout, (list) =>
    list.map((p) => (p.id === id ? { ...p, rows: clampRows(p.rows + delta) } : p)),
  );
}

/** Take a widget off the dashboard. */
export function removeWidget(layout: DashboardLayout, id: string): DashboardLayout {
  return mapZones(layout, (list) => list.filter((p) => p.id !== id));
}

/** Put a widget on the dashboard (no-op if already placed). */
export function addWidget(
  layout: DashboardLayout,
  id: string,
  zone: DashboardZone,
  rows: number,
): DashboardLayout {
  if (placedIds(layout).has(id)) return layout;
  return mapZones(layout, (list, z) =>
    z === zone ? [...list, { id, rows: clampRows(rows) }] : list,
  );
}

/**
 * Make an untrusted document (from storage) safe: drop unknown or duplicate
 * widgets and invalid sizes; fall back to the default when unusable.
 */
export function normalizeLayout(value: unknown, knownIds: ReadonlySet<string>): DashboardLayout {
  if (typeof value !== 'object' || value === null || !('zones' in value)) return DEFAULT_LAYOUT;
  const zones = (value as { zones: unknown }).zones;
  if (typeof zones !== 'object' || zones === null) return DEFAULT_LAYOUT;
  const seen = new Set<string>();
  const clean = (list: unknown): Placement[] =>
    (Array.isArray(list) ? list : []).flatMap((item): Placement[] => {
      if (typeof item !== 'object' || item === null) return [];
      const { id, rows } = item as { id?: unknown; rows?: unknown };
      if (typeof id !== 'string' || !knownIds.has(id) || seen.has(id)) return [];
      seen.add(id);
      return [{ id, rows: clampRows(typeof rows === 'number' ? rows : 2) }];
    });
  const record = zones as Record<string, unknown>;
  return { version: 1, zones: { left: clean(record.left), right: clean(record.right) } };
}
