import type { WidgetDefinition } from '@jarvis/widget-sdk';
import { motion } from 'motion/react';
import { Component, type ErrorInfo, type ReactNode } from 'react';

import { GlassPanel } from '../components/ui/GlassPanel';
import { cn } from '../lib/cn';
import { DEFAULT_LAYOUT, type DashboardLayout, type DashboardZone as Zone } from './layout';
import { widgetRegistry } from './registry';

/** Height of one grid row in px (see WidgetSize.rows). */
const ROW_HEIGHT = 96;
const GAP = 16;

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

function WidgetTile({ widget, index }: { widget: WidgetDefinition; index: number }) {
  const { manifest, component: Widget } = widget;
  // Zones are single-column stacks today; `cols` takes effect with the
  // free-form grid planned for Phase 4. A 4-row widget fills leftover height.
  const { rows } = manifest.defaultSize;
  const fills = rows === 4;
  const isApp = manifest.source.kind === 'mobile-app';

  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, delay: 0.15 + index * 0.07, ease: [0.22, 1, 0.36, 1] }}
      className={cn(fills ? 'min-h-[18rem] flex-1' : 'shrink-0')}
      style={fills ? undefined : { height: rows * ROW_HEIGHT + (rows - 1) * GAP }}
    >
      <GlassPanel
        title={manifest.name}
        className="h-full"
        accessory={
          isApp ? (
            <span className="rounded-full border border-white/10 px-2 py-0.5 font-mono text-[9px] tracking-wider text-white/30 uppercase">
              App
            </span>
          ) : undefined
        }
      >
        <WidgetErrorBoundary>
          <Widget size={manifest.defaultSize} />
        </WidgetErrorBoundary>
      </GlassPanel>
    </motion.div>
  );
}

interface Props {
  readonly zone: Zone;
  readonly layout?: DashboardLayout;
  readonly className?: string;
}

/** Renders the widgets assigned to one side of the dashboard. */
export function DashboardZone({ zone, layout = DEFAULT_LAYOUT, className }: Props) {
  const widgets = layout[zone]
    .map((id) => widgetRegistry.get(id))
    .filter((w): w is WidgetDefinition => w !== undefined);

  return (
    <aside className={cn('flex min-h-0 flex-col gap-4', className)}>
      {widgets.map((widget, index) => (
        <WidgetTile key={widget.manifest.id} widget={widget} index={index} />
      ))}
    </aside>
  );
}
