import { type WidgetDefinition, type WidgetSize, defineWidget } from '@jarvis/widget-sdk';

interface PlaceholderOptions {
  readonly id: string;
  readonly name: string;
  readonly description: string;
  /** Companion mobile app id that will provide the data. */
  readonly appId: string;
  readonly intents: readonly string[];
  readonly size?: WidgetSize;
}

const SKELETON_WIDTHS = ['w-4/5', 'w-3/5', 'w-2/3'];

/**
 * A tile reserved for a widget whose data will come from one of your mobile
 * apps. It already carries a real manifest (source, endpoint, voice intents),
 * so replacing it later only means swapping the component.
 */
export function createAppPlaceholder(options: PlaceholderOptions): WidgetDefinition {
  function AppPlaceholder() {
    return (
      <div className="flex flex-1 flex-col justify-between">
        <div className="space-y-3 pt-1">
          {SKELETON_WIDTHS.map((width) => (
            <div key={width} className="flex items-center gap-3">
              <span className="size-3 rounded-[4px] border border-white/10" />
              <span className={`skeleton h-2.5 rounded-full ${width}`} />
            </div>
          ))}
        </div>
        <p className="font-mono text-[10px] tracking-[0.18em] text-white/25 uppercase">
          Awaiting link · {options.appId}
        </p>
      </div>
    );
  }
  AppPlaceholder.displayName = `${options.name}Placeholder`;

  return defineWidget({
    manifest: {
      id: options.id,
      name: options.name,
      description: options.description,
      version: '0.0.1',
      defaultSize: options.size ?? { cols: 2, rows: 2 },
      source: { kind: 'mobile-app', appId: options.appId, endpoint: `/api/apps/${options.id}` },
      permissions: ['network', 'voice-intents'],
      voiceIntents: options.intents,
    },
    component: AppPlaceholder,
  });
}
