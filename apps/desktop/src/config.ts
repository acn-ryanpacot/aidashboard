/**
 * Front-end runtime configuration (from Vite env vars, see `.env.example`).
 *
 * @module
 */

const LOCAL_CORE = 'http://127.0.0.1:8765';

/**
 * Where the core service is, given how this page was loaded:
 *
 * - `VITE_JARVIS_CORE_URL` wins when set;
 * - the Vite dev server and the Tauri window talk to the core on this PC;
 * - a page served *by* the core (a phone through `tailscale serve`, or
 *   `http://127.0.0.1:8765/`) uses its own origin, so it works over HTTPS.
 */
export function resolveCoreUrl(
  location: Pick<Location, 'protocol' | 'host' | 'hostname'> | undefined,
  { override, dev }: { override?: string; dev: boolean },
): string {
  if (override) return override.replace(/\/$/, '');
  if (!location || dev) return LOCAL_CORE;
  const tauri = location.protocol === 'tauri:' || location.hostname === 'tauri.localhost';
  if (tauri || !location.protocol.startsWith('http')) return LOCAL_CORE;
  return `${location.protocol}//${location.host}`;
}

/** Base URL of the core service. */
export const CORE_HTTP_URL: string = resolveCoreUrl(
  typeof window === 'undefined' ? undefined : window.location,
  { override: import.meta.env.VITE_JARVIS_CORE_URL, dev: import.meta.env.DEV },
);

/** WebSocket URL of the voice endpoint (`wss://` when the page is HTTPS). */
export const VOICE_WS_URL = `${CORE_HTTP_URL.replace(/^http/, 'ws')}/ws/voice`;

/** Fallback user name until the core service reports it. */
export const DEFAULT_USER_NAME: string = import.meta.env.VITE_JARVIS_USER_NAME ?? 'Ryan';

/** App version shown in the status bar. */
export const APP_VERSION = '0.3.0';
