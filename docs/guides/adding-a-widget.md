# Adding a widget

A widget has two parts:

1. **A manifest**, which says what it is. It's plain JSON-like data, validated by `@jarvis/widget-sdk`.
2. **A component**, which says how it looks. It's a React component that receives `WidgetProps`.

## 1. Create the component

`apps/desktop/src/widgets/weather/WeatherWidget.tsx`:

```tsx
import type { WidgetProps } from '@jarvis/widget-sdk';

/** Current conditions from Open-Meteo (free, no API key). */
export function WeatherWidget(_props: WidgetProps) {
  // Fetch from the core service (e.g. /api/weather), never directly from the internet,
  // so caching, secrets and offline behaviour live in one place.
  return <p className="text-4xl font-extralight">18°</p>;
}
```

## 2. Define it

`apps/desktop/src/widgets/weather/index.ts`:

```ts
import { defineWidget } from '@jarvis/widget-sdk';

import { WeatherWidget } from './WeatherWidget';

export default defineWidget({
  manifest: {
    id: 'weather',
    name: 'Weather',
    description: 'Current conditions and the next few hours.',
    version: '1.0.0',
    defaultSize: { cols: 2, rows: 2 },
    minRows: 2, // the layout editor won't shrink it below this
    source: { kind: 'builtin' },
    permissions: ['network', 'location'],
    voiceIntents: ['weather.current'],
  },
  component: WeatherWidget,
});
```

`defineWidget` validates the manifest when the module is imported. A malformed id or version throws immediately instead of producing a broken tile.

## 3. Register it (and optionally place it by default)

Registered widgets appear in **Edit layout → Add widget**; users place and size them themselves.

```ts
// src/dashboard/registry.ts
import weather from '../widgets/weather';
// …
  .register(weather)

// src/state/layout.ts (optional: show it by default)
left: [{ id: 'clock', rows: 2 }, { id: 'weather', rows: 2 }],
```

## Widgets from your mobile apps

Use `source: { kind: 'mobile-app', appId, endpoint }`. `createAppPlaceholder` (in `src/widgets/placeholders/`) builds a reserved tile with a real manifest while the app is in development. When a mobile app is ready:

1. Add a router in the core service, e.g. `GET /api/apps/tasks`, that syncs with the app's backend.
2. Replace the placeholder's component with a real one that reads that endpoint.
3. Implement its `voiceIntents` as LLM tools (Phase 3), so you can say *"Jarvis, add milk to my list."*

## Checklist

- [ ] Kebab-case `id`, semver `version`
- [ ] TSDoc on the component
- [ ] Looks right at its `defaultSize`, with empty, loading and error states
- [ ] Unit tests for any non-trivial logic (keep logic out of the component)
