import type { WidgetDefinition } from '@jarvis/widget-sdk';
import { GripVertical, Minus, Plus, X } from 'lucide-react';
import { motion } from 'motion/react';
import { Component, type DragEvent, type ErrorInfo, type ReactNode, useState } from 'react';

import { GlassPanel } from '../components/ui/GlassPanel';
import { cn } from '../lib/cn';
import {
  type DashboardZone as Zone,
  type Placement,
  moveWidget,
  removeWidget,
  resizeWidget,
} from '../state/layout';
import { useUi } from '../state/uiStore';
import { useLayout } from './layoutStore';
import { widgetRegistry } from './registry';

/** Height of one grid row in px (see WidgetSize.rows). */
const ROW_HEIGHT = 96;
const GAP = 16;
const DRAG_MIME = 'application/x-jarvis-widget';

/** Isolates widget crashes so one broken tile can't take down the HUD. */
class WidgetErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  override state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  override componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Widget crashed', error, info.componentStack);
  }

  override render() {
    return this.state.failed ? (
      <p className="m-auto text-xs text-signal-red/70">This widget stopped responding.</p>
    ) : (
      this.props.children
    );
  }
}

interface TileProps {
  readonly widget: WidgetDefinition;
  readonly placement: Placement;
  readonly index: number;
  readonly editing: boolean;
  readonly onDragOverTile: (event: DragEvent<HTMLElement>, index: number) => void;
}

function EditButton(props: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={props.onClick}
      disabled={props.disabled}
      aria-label={props.label}
      title={props.label}
      className="flex size-6 items-center justify-center rounded-md text-white/50 transition hover:bg-white/10 hover:text-white disabled:opacity-25"
    >
      {props.children}
    </button>
  );
}

function WidgetTile({ widget, placement, index, editing, onDragOverTile }: TileProps) {
  const { manifest, component: Widget } = widget;
  const update = useLayout((s) => s.update);
  const minRows = manifest.minRows ?? 1;
  const rows = Math.max(placement.rows, minRows) as Placement['rows'];
  const fills = rows === 4;
  const isApp = manifest.source.kind === 'mobile-app';

  const accessory = editing ? (
    <div className="flex items-center gap-0.5">
      <EditButton
        label="Shorter"
        disabled={rows <= minRows}
        onClick={() => update((l) => resizeWidget(l, manifest.id, -1))}
      >
        <Minus className="size-3.5" />
      </EditButton>
      <EditButton
        label={rows === 3 ? 'Fill height' : 'Taller'}
        disabled={rows >= 4}
        onClick={() => update((l) => resizeWidget(l, manifest.id, 1))}
      >
        <Plus className="size-3.5" />
      </EditButton>
      <EditButton
        label={`Remove ${manifest.name}`}
        onClick={() => update((l) => removeWidget(l, manifest.id))}
      >
        <X className="size-3.5" />
      </EditButton>
    </div>
  ) : isApp ? (
    <span className="rounded-full border border-white/10 px-2 py-0.5 font-mono text-[9px] tracking-wider text-white/30 uppercase">
      App
    </span>
  ) : undefined;

  // Native HTML drag-and-drop lives on a plain element; Motion only animates
  // (its own `onDragStart` gesture API has a different signature).
  return (
    <div
      className={cn(fills ? 'min-h-[14rem] flex-1' : 'shrink-0', editing && 'cursor-grab')}
      style={fills ? undefined : { height: rows * ROW_HEIGHT + (rows - 1) * GAP }}
      draggable={editing}
      onDragStart={(event: DragEvent<HTMLDivElement>) => {
        event.dataTransfer.setData(DRAG_MIME, manifest.id);
        event.dataTransfer.effectAllowed = 'move';
      }}
      onDragOver={(event: DragEvent<HTMLDivElement>) => onDragOverTile(event, index)}
    >
      <motion.div
        layout
        className="h-full"
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.1 + index * 0.05, ease: [0.22, 1, 0.36, 1] }}
      >
        <GlassPanel
          title={manifest.name}
          className={cn('h-full', editing && 'ring-1 ring-arc-400/25')}
          accessory={accessory}
        >
          {editing && (
            <GripVertical className="pointer-events-none absolute top-4 left-1.5 size-3.5 text-white/25" />
          )}
          <WidgetErrorBoundary>
            <Widget size={{ cols: 2, rows }} />
          </WidgetErrorBoundary>
        </GlassPanel>
      </motion.div>
    </div>
  );
}

interface Props {
  readonly zone: Zone;
  readonly className?: string;
}

/** Renders (and, in edit mode, rearranges) the widgets of one dashboard side. */
export function DashboardZone({ zone, className }: Props) {
  const placements = useLayout((s) => s.layout.zones[zone]);
  const update = useLayout((s) => s.update);
  const setGalleryZone = useLayout((s) => s.setGalleryZone);
  const editing = useUi((s) => s.editing);
  const open = useUi((s) => s.open);
  const [dropIndex, setDropIndex] = useState<number | null>(null);

  const tiles = placements.flatMap((placement) => {
    const widget = widgetRegistry.get(placement.id);
    return widget ? [{ widget, placement }] : [];
  });

  const acceptsDrag = (event: DragEvent<HTMLElement>) =>
    editing && event.dataTransfer.types.includes(DRAG_MIME);

  const onDragOverTile = (event: DragEvent<HTMLElement>, index: number) => {
    if (!acceptsDrag(event)) return;
    event.preventDefault();
    event.stopPropagation();
    const box = event.currentTarget.getBoundingClientRect();
    setDropIndex(event.clientY < box.top + box.height / 2 ? index : index + 1);
  };

  const onDrop = (event: DragEvent<HTMLElement>) => {
    if (!acceptsDrag(event)) return;
    event.preventDefault();
    const id = event.dataTransfer.getData(DRAG_MIME);
    const target = dropIndex ?? tiles.length;
    setDropIndex(null);
    update((layout) => {
      // Moving down within the same zone: account for the gap the widget leaves.
      const current = layout.zones[zone].findIndex((p) => p.id === id);
      const index = current >= 0 && current < target ? target - 1 : target;
      return moveWidget(layout, id, zone, index);
    });
  };

  return (
    <aside
      className={cn(
        'hud-scroll -mr-2 flex min-h-0 flex-col gap-4 overflow-y-auto pr-2',
        editing && 'rounded-3xl',
        className,
      )}
      onDragOver={(event) => {
        if (!acceptsDrag(event)) return;
        event.preventDefault();
        if (dropIndex === null) setDropIndex(tiles.length);
      }}
      onDragLeave={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDropIndex(null);
      }}
      onDrop={onDrop}
      aria-label={`${zone} widgets`}
    >
      {tiles.map(({ widget, placement }, index) => (
        <div key={widget.manifest.id} className="contents">
          {editing && dropIndex === index && <DropMarker />}
          <WidgetTile
            widget={widget}
            placement={placement}
            index={index}
            editing={editing}
            onDragOverTile={onDragOverTile}
          />
        </div>
      ))}
      {editing && dropIndex === tiles.length && <DropMarker />}
      {editing && (
        <button
          type="button"
          onClick={() => {
            setGalleryZone(zone);
            open('gallery');
          }}
          className="flex h-14 shrink-0 items-center justify-center gap-2 rounded-2xl border border-dashed border-white/15 font-mono text-[11px] tracking-[0.2em] text-white/40 uppercase transition hover:border-arc-400/40 hover:text-arc-200"
        >
          <Plus className="size-4" /> Add widget
        </button>
      )}
    </aside>
  );
}

function DropMarker() {
  return (
    <div className="h-0.5 shrink-0 rounded-full bg-arc-400 shadow-[0_0_12px_rgb(var(--accent-rgb)/0.8)]" />
  );
}
