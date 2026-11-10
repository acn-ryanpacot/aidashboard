/**
 * Presentation state: theme, focus/ambient modes, layout editing and which
 * overlay is open. Appearance preferences persist in localStorage.
 *
 * @module
 */
import { create } from 'zustand';

/** Visual themes (see `styles/global.css`). */
export type Theme = 'arctic' | 'stark' | 'stealth';

export const THEMES: readonly { id: Theme; label: string; description: string }[] = [
  { id: 'arctic', label: 'Arctic', description: 'Cool cyan on midnight — the default.' },
  { id: 'stark', label: 'Stark Gold', description: 'Hot-rod red and gold.' },
  { id: 'stealth', label: 'Stealth', description: 'Monochrome, low-glare.' },
];

/** Which modal surface is showing (only one at a time). */
export type Overlay = 'none' | 'palette' | 'settings' | 'gallery';

interface Appearance {
  readonly theme: Theme;
  /** Minutes of inactivity before ambient mode; 0 = never. */
  readonly ambientAfterMin: number;
}

export interface UiState extends Appearance {
  readonly focus: boolean;
  readonly ambient: boolean;
  readonly editing: boolean;
  readonly overlay: Overlay;
  setTheme(theme: Theme): void;
  setAmbientAfter(minutes: number): void;
  setFocus(focus: boolean): void;
  setAmbient(ambient: boolean): void;
  setEditing(editing: boolean): void;
  open(overlay: Overlay): void;
  close(): void;
}

const STORAGE_KEY = 'jarvis.appearance';
const DEFAULT_APPEARANCE: Appearance = { theme: 'arctic', ambientAfterMin: 10 };

function loadAppearance(): Appearance {
  try {
    const raw = globalThis.localStorage?.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_APPEARANCE;
    const parsed = JSON.parse(raw) as Partial<Appearance>;
    return {
      theme: THEMES.some((t) => t.id === parsed.theme) ? (parsed.theme as Theme) : 'arctic',
      ambientAfterMin:
        typeof parsed.ambientAfterMin === 'number' && parsed.ambientAfterMin >= 0
          ? parsed.ambientAfterMin
          : DEFAULT_APPEARANCE.ambientAfterMin,
    };
  } catch {
    return DEFAULT_APPEARANCE;
  }
}

function saveAppearance(appearance: Appearance): void {
  try {
    globalThis.localStorage?.setItem(STORAGE_KEY, JSON.stringify(appearance));
  } catch {
    // Private mode / storage disabled: keep the setting for this session only.
  }
}

/** Global UI store (React hook). */
export const useUi = create<UiState>()((set, get) => ({
  ...loadAppearance(),
  focus: false,
  ambient: false,
  editing: false,
  overlay: 'none',
  setTheme: (theme) => {
    set({ theme });
    saveAppearance({ theme, ambientAfterMin: get().ambientAfterMin });
  },
  setAmbientAfter: (ambientAfterMin) => {
    set({ ambientAfterMin });
    saveAppearance({ theme: get().theme, ambientAfterMin });
  },
  setFocus: (focus) => set({ focus, editing: focus ? false : get().editing }),
  setAmbient: (ambient) => set({ ambient }),
  setEditing: (editing) => set({ editing, focus: editing ? false : get().focus }),
  open: (overlay) => set({ overlay }),
  close: () => set({ overlay: 'none' }),
}));
