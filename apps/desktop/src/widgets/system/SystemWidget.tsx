import { coreApi } from '../../core/api/client';
import { useCoreData } from '../../core/api/useCoreData';
import { cn } from '../../lib/cn';
import { formatUptime } from '../../lib/format';

const loadSystem = () => coreApi.getSystem();

function Meter({ label, value, detail }: { label: string; value: number; detail: string }) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between">
        <span className="font-mono text-[10px] tracking-[0.18em] text-white/40 uppercase">
          {label}
        </span>
        <span className="font-mono text-[11px] text-white/70 tabular-nums">{detail}</span>
      </div>
      <div className="h-1 overflow-hidden rounded-full bg-white/[0.06]">
        <div
          className={cn(
            'h-full rounded-full transition-[width] duration-700',
            pct > 85 ? 'bg-signal-red/80' : pct > 60 ? 'bg-gold-400/80' : 'bg-arc-400/80',
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

/** CPU, memory and GPU load of the machine running Jarvis. */
export function SystemWidget() {
  const { data, error } = useCoreData([], loadSystem, 5_000);
  if (error) return <p className="m-auto text-xs text-white/35">System monitor unavailable.</p>;
  if (!data) return null;
  const memoryPct = (data.memory_used_gb / data.memory_total_gb) * 100;
  return (
    <div className="flex flex-1 flex-col justify-center gap-3">
      <Meter label="CPU" value={data.cpu_percent} detail={`${Math.round(data.cpu_percent)}%`} />
      <Meter
        label="Memory"
        value={memoryPct}
        detail={`${data.memory_used_gb.toFixed(1)} / ${Math.round(data.memory_total_gb)} GB`}
      />
      {data.gpus.map((gpu) => (
        <Meter
          key={gpu.name}
          label={gpu.name.replace(/^NVIDIA (GeForce )?/, '')}
          value={(gpu.memory_used_mb / gpu.memory_total_mb) * 100}
          detail={`${Math.round(gpu.utilization_pct)}% · ${(gpu.memory_used_mb / 1024).toFixed(1)} GB${
            gpu.temperature_c !== null ? ` · ${Math.round(gpu.temperature_c)}°` : ''
          }`}
        />
      ))}
      <p className="font-mono text-[10px] text-white/30">Up {formatUptime(data.uptime_s)}</p>
    </div>
  );
}
