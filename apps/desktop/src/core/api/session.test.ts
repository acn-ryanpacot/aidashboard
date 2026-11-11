import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { QrCode } from '../../components/ui/QrCode';
import { resolveCoreUrl } from '../../config';
import { relativeAgo } from '../../lib/format';
import {
  authHeaders,
  consumePairingLink,
  deviceToken,
  markUnpaired,
  pairingStore,
  pairingTokenFrom,
  voiceSubprotocols,
} from './session';

describe('pairing link', () => {
  it('reads the token from the URL fragment', () => {
    expect(pairingTokenFrom('#pair=abc-123')).toBe('abc-123');
    expect(pairingTokenFrom('pair=abc')).toBe('abc');
    expect(pairingTokenFrom('#pair=')).toBeNull();
    expect(pairingTokenFrom('')).toBeNull();
  });

  describe('in a browser', () => {
    afterEach(() => vi.unstubAllGlobals());

    it('stores the token and removes it from the address bar', () => {
      const store = new Map<string, string>();
      vi.stubGlobal('localStorage', {
        getItem: (k: string) => store.get(k) ?? null,
        setItem: (k: string, v: string) => store.set(k, v),
        removeItem: (k: string) => store.delete(k),
      });
      const replaceState = vi.fn();
      vi.stubGlobal('window', { history: { replaceState } });
      const location = { hash: '#pair=tok-1', pathname: '/', search: '' } as Location;

      expect(consumePairingLink(location)).toBe(true);
      expect(deviceToken()).toBe('tok-1');
      expect(replaceState).toHaveBeenCalledWith(null, '', '/');
      expect(authHeaders()).toEqual({ Authorization: 'Bearer tok-1' });
      expect(voiceSubprotocols()).toEqual(['jarvis.v3', 'bearer.tok-1']);

      markUnpaired();
      expect(deviceToken()).toBeNull();
      expect(pairingStore.getState().needsPairing).toBe(true);
    });
  });
});

describe('auth on this PC', () => {
  it('sends no credentials without a token', () => {
    expect(authHeaders(null)).toEqual({});
    expect(voiceSubprotocols(null)).toEqual(['jarvis.v3']);
  });
});

describe('core URL', () => {
  const at = (protocol: string, host: string) => ({
    protocol,
    host,
    hostname: host.split(':')[0] ?? host,
  });

  it('uses the page origin when the core serves the UI', () => {
    expect(resolveCoreUrl(at('https:', 'jarvis-pc.tail1234.ts.net'), { dev: false })).toBe(
      'https://jarvis-pc.tail1234.ts.net',
    );
    expect(resolveCoreUrl(at('http:', '127.0.0.1:8765'), { dev: false })).toBe(
      'http://127.0.0.1:8765',
    );
  });

  it('talks to the local core from the dev server and the Tauri window', () => {
    expect(resolveCoreUrl(at('http:', 'localhost:5173'), { dev: true })).toBe(
      'http://127.0.0.1:8765',
    );
    expect(resolveCoreUrl(at('tauri:', 'localhost'), { dev: false })).toBe('http://127.0.0.1:8765');
    expect(resolveCoreUrl(at('http:', 'tauri.localhost'), { dev: false })).toBe(
      'http://127.0.0.1:8765',
    );
    expect(resolveCoreUrl(undefined, { dev: false })).toBe('http://127.0.0.1:8765');
  });

  it('honours an explicit override', () => {
    expect(
      resolveCoreUrl(at('https:', 'x.ts.net'), { dev: false, override: 'http://10.0.0.2:8765/' }),
    ).toBe('http://10.0.0.2:8765');
  });
});

describe('pairing QR code', () => {
  it('renders a square grid of dark modules as SVG', () => {
    const svg = renderToStaticMarkup(
      createElement(QrCode, { value: 'https://jarvis-pc.tail1234.ts.net/#pair=abc', label: 'QR' }),
    );
    const size = Number(/viewBox="0 0 (\d+) \1"/.exec(svg)?.[1]);
    expect(size).toBeGreaterThanOrEqual(25); // version 2+ plus the border
    expect((svg.match(/<rect /g) ?? []).length).toBeGreaterThan(100);
    expect(svg).toContain('aria-label="QR"');
  });
});

describe('relativeAgo', () => {
  it('phrases the past', () => {
    const now = new Date('2026-11-11T10:00:00Z');
    expect(relativeAgo('2026-11-11T09:59:40Z', now)).toBe('just now');
    expect(relativeAgo('2026-11-11T09:45:00Z', now)).toBe('15 min ago');
    expect(relativeAgo('2026-11-11T07:00:00Z', now)).toBe('3 h ago');
    expect(relativeAgo('2026-11-08T10:00:00Z', now)).toBe('3 d ago');
  });
});
