import { Check, Plus } from 'lucide-react';

import { Modal } from '../components/ui/Modal';
import { addWidget, placedIds } from '../state/layout';
import { useUi } from '../state/uiStore';
import { useLayout } from './layoutStore';
import { widgetRegistry } from './registry';

/** Lists every registered widget; click one to add it to the chosen side. */
export function WidgetGallery() {
  const overlay = useUi((s) => s.overlay);
  const close = useUi((s) => s.close);
  const layout = useLayout((s) => s.layout);
  const zone = useLayout((s) => s.galleryZone);
  const update = useLayout((s) => s.update);
  const placed = placedIds(layout);

  return (
    <Modal open={overlay === 'gallery'} onClose={close} title={`Add a widget · ${zone} side`}>
      <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {widgetRegistry.list().map(({ manifest }) => {
          const isPlaced = placed.has(manifest.id);
          return (
            <li key={manifest.id}>
              <button
                type="button"
                disabled={isPlaced}
                onClick={() => {
                  update((l) => addWidget(l, manifest.id, zone, manifest.defaultSize.rows));
                  close();
                }}
                className="flex h-full w-full items-start gap-3 rounded-xl border border-white/8 bg-white/[0.02] p-3 text-left transition hover:border-arc-400/40 hover:bg-white/[0.05] disabled:cursor-default disabled:opacity-45"
              >
                <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-lg bg-white/5 text-arc-300">
                  {isPlaced ? <Check className="size-3.5" /> : <Plus className="size-3.5" />}
                </span>
                <span>
                  <span className="block text-[13.5px] text-white/90">{manifest.name}</span>
                  <span className="block text-[12px] leading-snug text-white/40">
                    {isPlaced ? 'Already on the dashboard' : manifest.description}
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </Modal>
  );
}
