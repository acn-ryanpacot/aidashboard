/**
 * Front-end runtime configuration (from Vite env vars, see `.env.example`).
 *
 * @module
 */

/** Base URL of the core service. */
export const CORE_HTTP_URL: string = (
  import.meta.env.VITE_JARVIS_CORE_URL ?? 'http://127.0.0.1:8765'
).replace(/\/$/, '');

/** WebSocket URL of the voice endpoint. */
export const VOICE_WS_URL = `${CORE_HTTP_URL.replace(/^http/, 'ws')}/ws/voice`;

/** Fallback user name until the core service reports it. */
export const DEFAULT_USER_NAME: string = import.meta.env.VITE_JARVIS_USER_NAME ?? 'Ryan';

/** App version shown in the status bar. */
export const APP_VERSION = '0.1.0';
