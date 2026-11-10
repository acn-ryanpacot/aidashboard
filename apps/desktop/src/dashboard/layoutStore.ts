/**
 * The live dashboard layout, saved to the core service so it follows you
 * between the desktop app, a browser tab and (later) other devices.
 *
 * - Every change is written to localStorage immediately and to
 *   `/api/ui-preferences/layout` after a short debounce.
 * - On connect, the server copy wins (if one exists).
 *
 * @module
 */
import { create } from 'zustand';

import { coreApi } from '../core/api/client';
import {
  DEFAULT_LAYOUT,
  type DashboardLayout,
  type DashboardZone,
  normalizeLayout,
} from '../state/layout';
import { KNOWN_WIDGET_IDS } from './registry';

const LOCAL_KEY = 'jarvis.layout';
const SAVE_DELAY_MS = 600;

interface LayoutState {
  readonly layout: DashboardLayout;
  /** Zone the "Add widget" gallery adds to. */
  readonly galleryZone: DashboardZone;
  update(change: (layout: DashboardLayout) => DashboardLayout): void;
  hydrate(value: unknown): void;
  reset(): void;
  setGalleryZone(zone: DashboardZone): void;
}

function readLocal(): DashboardLayout {
  try {
    const raw = globalThis.localStorage?.getItem(LOCAL_KEY);
    return raw ? normalizeLayout(JSON.parse(raw), KNOWN_WIDGET_IDS) : DEFAULT_LAYOUT;
  } catch {
    return DEFAULT_LAYOUT;
  }
}

let saveTimer: ReturnType<typeof setTimeout> | null = null;

function persist(layout: DashboardLayout): void {
  try {
    globalThis.localStorage?.setItem(LOCAL_KEY, JSON.stringify(layout));
  } catch {
    // Storage unavailable: the server copy still persists it.
  }
  if (saveTimer) clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    coreApi.putUiPreference('layout', layout).catch((error: unknown) => {
      console.warn('Could not save the layout to the core service', error);
    });
  }, SAVE_DELAY_MS);
}

/** Global layout store (React hook). */
export const useLayout = create<LayoutState>()((set, get) => ({
  layout: readLocal(),
  galleryZone: 'right',
  update: (change) => {
    const next = change(get().layout);
    if (next === get().layout) return;
    set({ layout: next });
    persist(next);
  },
  hydrate: (value) => {
    if (value === null || value === undefined) {
      persist(get().layout); // first run against this core: upload the local layout
      return;
    }
    const layout = normalizeLayout(value, KNOWN_WIDGET_IDS);
    set({ layout });
    try {
      globalThis.localStorage?.setItem(LOCAL_KEY, JSON.stringify(layout));
    } catch {
      // ignore
    }
  },
  reset: () => {
    set({ layout: DEFAULT_LAYOUT });
    persist(DEFAULT_LAYOUT);
  },
  setGalleryZone: (galleryZone) => set({ galleryZone }),
}));
