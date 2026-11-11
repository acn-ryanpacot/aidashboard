import { useStore } from 'zustand';
import { type FormEvent, useState } from 'react';

import { pairingStore, saveDeviceToken } from '../../core/api/session';

/**
 * Shown on a phone that isn't paired (or whose pairing was revoked). Pairing
 * happens on the PC: Settings → Phone access shows a QR code that opens
 * Jarvis here with the token. Pasting the token works too.
 */
export function PairingScreen() {
  const needsPairing = useStore(pairingStore, (s) => s.needsPairing);
  const [token, setToken] = useState('');

  if (!needsPairing) return null;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!token.trim()) return;
    saveDeviceToken(token);
    window.location.reload(); // start fresh with the token
  };

  return (
    <div className="fixed inset-0 z-[60] flex flex-col items-center justify-center bg-void/95 px-8 text-center backdrop-blur-2xl">
      <div className="engage-core mb-10 scale-75" aria-hidden />
      <h1 className="mb-3 pl-[0.5em] text-xl font-light tracking-[0.5em] text-white/90">JARVIS</h1>
      <p className="mb-8 max-w-sm text-[14px] leading-relaxed text-white/60">
        This device isn’t paired yet. On your PC, open Jarvis →{' '}
        <span className="text-arc-200">Settings → Phone access → Pair a phone</span>, then scan the
        QR code with this phone’s camera.
      </p>
      <form onSubmit={submit} className="flex w-full max-w-sm flex-col gap-3">
        <input
          value={token}
          onChange={(e) => setToken(e.target.value)}
          placeholder="…or paste the device token"
          aria-label="Device token"
          autoComplete="off"
          spellCheck={false}
          className="h-11 rounded-xl border border-white/10 bg-white/[0.04] px-4 font-mono text-[13px] text-white/85 placeholder:text-white/25 focus:border-arc-400/50 focus:outline-none"
        />
        <button
          type="submit"
          disabled={!token.trim()}
          className="engage-button rounded-full py-3 text-sm font-medium tracking-[0.25em] text-void uppercase disabled:opacity-40"
        >
          Pair
        </button>
      </form>
    </div>
  );
}
