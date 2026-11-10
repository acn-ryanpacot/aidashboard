import { X } from 'lucide-react';
import { useState } from 'react';

import { coreApi } from '../../core/api/client';
import { useCoreData } from '../../core/api/useCoreData';

const loadMemories = () => coreApi.listMemories();

/** Everything Jarvis remembers about you — and a way to make it forget. */
export function MemoriesWidget() {
  const { data, error, reload } = useCoreData(['memories'], loadMemories);
  const [forgetting, setForgetting] = useState<number | null>(null);

  const forget = async (id: number) => {
    setForgetting(id);
    try {
      await coreApi.deleteMemory(id);
    } finally {
      setForgetting(null);
      reload();
    }
  };

  if (error) return <p className="m-auto text-xs text-white/35">Memory unavailable.</p>;
  if (data?.length === 0) {
    return (
      <p className="m-auto max-w-[15rem] text-center text-[13px] leading-relaxed text-white/35">
        Nothing remembered yet. Try “Jarvis, remember that my passport expires in March.”
      </p>
    );
  }
  return (
    <ul className="hud-scroll -mr-2 flex-1 space-y-2 overflow-y-auto pr-2">
      {(data ?? []).map((memory) => (
        <li key={memory.id} className="group flex items-start gap-2">
          <span className="mt-1.5 size-1 shrink-0 rounded-full bg-arc-400/60" />
          <span className="flex-1 text-[13px] leading-snug text-white/80">{memory.text}</span>
          <button
            type="button"
            onClick={() => void forget(memory.id)}
            disabled={forgetting === memory.id}
            aria-label={`Forget: ${memory.text}`}
            title="Forget"
            className="text-white/0 transition group-hover:text-white/40 hover:text-signal-red/80"
          >
            <X className="size-3.5" />
          </button>
        </li>
      ))}
    </ul>
  );
}
