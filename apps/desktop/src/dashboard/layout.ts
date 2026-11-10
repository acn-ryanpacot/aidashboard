/**
 * Where each widget sits. Kept separate from the widgets themselves so the
 * layout can later be user-editable and persisted (Phase 4: drag & resize).
 *
 * @module
 */

/** The dashboard's side columns flanking the central core. */
export type DashboardZone = 'left' | 'right';

/** Ordered widget ids per zone. */
export type DashboardLayout = Readonly<Record<DashboardZone, readonly string[]>>;

export const DEFAULT_LAYOUT: DashboardLayout = {
  left: ['clock', 'core-link', 'schedule'],
  right: ['conversation', 'tasks', 'news'],
};
