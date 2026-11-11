/**
 * Device pairing for phone access (see docs/guides/phone-access.md).
 *
 * On this PC nothing is needed: the core trusts loopback. A phone opening
 * Jarvis through `tailscale serve` must present the device token it got when
 * it was paired. The token arrives once in the URL fragment (`#pair=…`,
 * which never reaches any server), is kept in `localStorage`, and is sent as
 * `Authorization: Bearer …` (HTTP) or a `bearer.…` subprotocol (WebSocket).
 *
 * @module
 */
import { createStore } from 'zustand/vanilla';

const STORAGE_KEY = 'jarvis.deviceToken';

/** WebSocket subprotocol spoken by Jarvis clients (echoed by the core). */
export const WS_PROTOCOL = 'jarvis.v3';
/** Close code the core uses for a remote device without a valid token. */
export const UNPAIRED_CLOSE_CODE = 4401;

interface PairingState {
  /** `true` once the core has refused this device (no or revoked token). */
  readonly needsPairing: boolean;
}

/** Observable pairing state (the HUD shows the pairing screen when needed). */
export const pairingStore = createStore<PairingState>(() => ({ needsPairing: false }));

function storage(): Storage | null {
  try {
    return typeof localStorage === 'undefined' ? null : localStorage;
  } catch {
    return null; // e.g. storage disabled
  }
}

/** The stored device token, if this browser has been paired. */
export function deviceToken(): string | null {
  return storage()?.getItem(STORAGE_KEY) || null;
}

/** Remember a device token (e.g. pasted on the pairing screen). */
export function saveDeviceToken(token: string): void {
  storage()?.setItem(STORAGE_KEY, token.trim());
  pairingStore.setState({ needsPairing: false });
}

/** Forget the token (the core rejected it). */
export function markUnpaired(): void {
  storage()?.removeItem(STORAGE_KEY);
  pairingStore.setState({ needsPairing: true });
}

/** The token in a `#pair=<token>` fragment, if any. */
export function pairingTokenFrom(hash: string): string | null {
  const params = new URLSearchParams(hash.replace(/^#/, ''));
  const token = params.get('pair')?.trim();
  return token ? token : null;
}

/**
 * Store a token delivered in the URL (`…/#pair=<token>` from the QR code),
 * then remove it from the address bar and history so it isn't bookmarked.
 *
 * @returns Whether a token was found.
 */
export function consumePairingLink(location: Location = window.location): boolean {
  const token = pairingTokenFrom(location.hash);
  if (!token) return false;
  saveDeviceToken(token);
  window.history.replaceState(null, '', `${location.pathname}${location.search}`);
  return true;
}

/** Extra HTTP headers for a request to the core. */
export function authHeaders(token: string | null = deviceToken()): Record<string, string> {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** Subprotocols to offer when opening the voice WebSocket. */
export function voiceSubprotocols(token: string | null = deviceToken()): string[] {
  return token ? [WS_PROTOCOL, `bearer.${token}`] : [WS_PROTOCOL];
}
