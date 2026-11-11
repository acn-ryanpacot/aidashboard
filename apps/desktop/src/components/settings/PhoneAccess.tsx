import { Check, Copy, Smartphone, X } from 'lucide-react';
import { type FormEvent, type ReactNode, useCallback, useEffect, useState } from 'react';

import {
  ApiError,
  type Device,
  type PairedDevice,
  type RemoteStatus,
  coreApi,
} from '../../core/api/client';
import { cn } from '../../lib/cn';
import { relativeAgo } from '../../lib/format';
import { QrCode } from '../ui/QrCode';

function Step({ done, title, hint }: { done: boolean; title: string; hint?: ReactNode }) {
  return (
    <li className="flex gap-2.5">
      <span
        className={cn(
          'mt-0.5 flex size-4 shrink-0 items-center justify-center rounded-full border text-[9px]',
          done ? 'border-arc-400/60 text-arc-300' : 'border-white/15 text-transparent',
        )}
      >
        <Check className="size-2.5" strokeWidth={3} />
      </span>
      <div className="min-w-0">
        <p className={cn('text-[12.5px]', done ? 'text-white/75' : 'text-white/55')}>{title}</p>
        {!done && hint && <p className="mt-0.5 text-[11.5px] text-white/35">{hint}</p>}
      </div>
    </li>
  );
}

const code = (text: string) => <code className="font-mono text-arc-200/80">{text}</code>;

/**
 * Settings → Phone access: setup checklist, pairing with a QR code, and the
 * list of paired devices. The Settings panel shows it only on this PC
 * (the core refuses device management from phones anyway).
 */
export function PhoneAccess() {
  const [remote, setRemote] = useState<RemoteStatus | null>(null);
  const [devices, setDevices] = useState<readonly Device[]>([]);
  const [name, setName] = useState('My phone');
  const [paired, setPaired] = useState<PairedDevice | null>(null);
  const [copied, setCopied] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [status, list] = await Promise.all([coreApi.getRemoteStatus(), coreApi.listDevices()]);
      setRemote(status);
      setDevices(list);
    } catch (reason) {
      setProblem(reason instanceof ApiError ? reason.message : "Couldn't load devices.");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const pair = async (event: FormEvent) => {
    event.preventDefault();
    setProblem(null);
    try {
      setPaired(await coreApi.pairDevice(name.trim() || 'Phone'));
      setCopied(false);
      await refresh();
    } catch (reason) {
      setProblem(reason instanceof ApiError ? reason.message : "Couldn't pair the device.");
    }
  };

  const revoke = async (id: number) => {
    await coreApi.revokeDevice(id).catch(() => undefined);
    if (paired?.id === id) setPaired(null);
    await refresh();
  };

  const copy = async (text: string) => {
    await navigator.clipboard.writeText(text).catch(() => undefined);
    setCopied(true);
  };

  const port = remote?.port ?? 8765;
  return (
    <div className="space-y-5">
      <ol className="space-y-2.5">
        <Step
          done={Boolean(remote?.installed && remote.running)}
          title={
            remote?.running ? `Tailscale connected as ${remote.dns_name}` : 'Tailscale on this PC'
          }
          hint={
            remote?.installed ? (
              <>Sign in to Tailscale on this PC ({code('tailscale up')}).</>
            ) : (
              <>
                Install Tailscale (free) on this PC and your phone, signed in with the same account.
              </>
            )
          }
        />
        <Step
          done={Boolean(remote?.public_url)}
          title={
            remote?.public_url
              ? `Published at ${remote.public_url}`
              : 'Publish Jarvis to your phone'
          }
          hint={<>In a terminal on this PC: {code(`tailscale serve --bg ${port}`)}</>}
        />
        <Step
          done={Boolean(remote?.web_ui)}
          title="Dashboard built for phones"
          hint={
            <>
              From the repository folder: {code('pnpm --filter @jarvis/desktop build')}, then
              restart the core.
            </>
          }
        />
      </ol>

      {paired ? (
        <div className="flex flex-col items-center gap-3 rounded-2xl border border-arc-400/20 bg-white/[0.02] p-4 text-center">
          {paired.pair_url ? (
            <>
              <QrCode value={paired.pair_url} label="Pairing QR code" />
              <p className="text-[12px] text-white/60">
                Scan with <span className="text-white/85">{paired.name}</span>’s camera. It opens
                Jarvis and pairs it.
              </p>
            </>
          ) : (
            <p className="text-[12px] text-white/60">
              Finish the steps above to get a QR code, or open Jarvis on the phone and paste this
              token:
            </p>
          )}
          <button
            type="button"
            onClick={() => void copy(paired.pair_url || paired.token)}
            className="flex max-w-full items-center gap-2 rounded-lg bg-white/[0.04] px-3 py-1.5 font-mono text-[10.5px] text-white/55 hover:text-white/85"
            title="Copy"
          >
            <span className="truncate">{paired.pair_url ? 'Copy pairing link' : paired.token}</span>
            {copied ? (
              <Check className="size-3.5 shrink-0" />
            ) : (
              <Copy className="size-3.5 shrink-0" />
            )}
          </button>
          <p className="text-[11px] text-white/35">
            Shown only once. It works like a password; revoke the device below if it leaks.
          </p>
          <button
            type="button"
            onClick={() => setPaired(null)}
            className="text-[12px] text-white/45 hover:text-white/80"
          >
            Done
          </button>
        </div>
      ) : (
        <form onSubmit={(e) => void pair(e)} className="flex items-center gap-2">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            aria-label="Device name"
            maxLength={60}
            className="h-9 min-w-0 flex-1 rounded-lg border border-white/10 bg-white/[0.03] px-3 text-[13px] text-white/85 focus:border-arc-400/50 focus:outline-none"
          />
          <button
            type="submit"
            className="flex h-9 shrink-0 items-center gap-1.5 rounded-lg bg-arc-400/90 px-3.5 text-[12px] font-medium text-void transition hover:bg-arc-300"
          >
            <Smartphone className="size-3.5" /> Pair a phone
          </button>
        </form>
      )}
      {problem && <p className="text-[11.5px] text-signal-red/80">{problem}</p>}

      {devices.length > 0 && (
        <ul className="space-y-1.5">
          {devices.map((device) => (
            <li key={device.id} className="group flex items-center gap-2.5 text-[12.5px]">
              <Smartphone className="size-3.5 shrink-0 text-white/35" />
              <span className="truncate text-white/75">{device.name}</span>
              <span className="ml-auto shrink-0 font-mono text-[10px] text-white/35">
                {device.last_used_at ? `used ${relativeAgo(device.last_used_at)}` : 'not used yet'}
              </span>
              <button
                type="button"
                onClick={() => void revoke(device.id)}
                aria-label={`Revoke ${device.name}`}
                title="Revoke"
                className="text-white/25 transition hover:text-signal-red/80"
              >
                <X className="size-3.5" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
