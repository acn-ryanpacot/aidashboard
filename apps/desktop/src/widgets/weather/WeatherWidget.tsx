import {
  Cloud,
  CloudDrizzle,
  CloudFog,
  CloudLightning,
  CloudRain,
  CloudSnow,
  CloudSun,
  Droplets,
  Sun,
  Wind,
} from 'lucide-react';
import type { ComponentType } from 'react';

import { coreApi } from '../../core/api/client';
import { useCoreData } from '../../core/api/useCoreData';
import { useUi } from '../../state/uiStore';

const loadWeather = () => coreApi.getWeather();

/** Pick an icon for an Open-Meteo description. */
function weatherIcon(description: string): ComponentType<{ className?: string }> {
  const d = description.toLowerCase();
  if (d.includes('thunder')) return CloudLightning;
  if (d.includes('snow')) return CloudSnow;
  if (d.includes('drizzle')) return CloudDrizzle;
  if (d.includes('rain') || d.includes('shower')) return CloudRain;
  if (d.includes('fog')) return CloudFog;
  if (d.includes('clear')) return Sun;
  if (d.includes('partly') || d.includes('mainly')) return CloudSun;
  return Cloud;
}

/** Current conditions at the home location (set in Settings → Brain). */
export function WeatherWidget() {
  const { data, error, loaded } = useCoreData(['settings'], loadWeather, 10 * 60_000);
  const openSettings = useUi((s) => s.open);

  if (error) return <p className="m-auto text-xs text-white/35">Weather unavailable.</p>;
  if (!loaded) return null;
  if (data === null) {
    return (
      <button
        type="button"
        onClick={() => openSettings('settings')}
        className="m-auto text-center text-[13px] text-white/40 hover:text-white/70"
      >
        Set your home location in Settings to see the weather.
      </button>
    );
  }
  const Icon = weatherIcon(data.description);
  return (
    <div className="flex flex-1 items-center gap-4">
      <Icon className="size-12 shrink-0 text-arc-300/80" />
      <div className="min-w-0 flex-1">
        <p className="flex items-baseline gap-2">
          <span className="text-[40px] leading-none font-extralight text-white tabular-nums">
            {Math.round(data.temperature_c)}°
          </span>
          {data.high_c !== null && data.low_c !== null && (
            <span className="font-mono text-[11px] text-white/40">
              {Math.round(data.high_c)}° / {Math.round(data.low_c)}°
            </span>
          )}
        </p>
        <p className="mt-1 truncate text-[13px] text-white/70 capitalize">{data.description}</p>
        <p className="mt-1.5 flex items-center gap-3 font-mono text-[10px] text-white/35">
          <span className="truncate">{data.location}</span>
          <span className="flex items-center gap-1">
            <Wind className="size-3" />
            {Math.round(data.wind_kph)}
          </span>
          <span className="flex items-center gap-1">
            <Droplets className="size-3" />
            {Math.round(data.humidity_pct)}%
          </span>
        </p>
      </div>
    </div>
  );
}
