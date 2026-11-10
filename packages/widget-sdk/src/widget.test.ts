import { describe, expect, it } from 'vitest';

import { type WidgetManifest, validateManifest } from './manifest';
import { WidgetDefinitionError, WidgetRegistry, defineWidget } from './widget';

const manifest: WidgetManifest = {
  id: 'tasks-today',
  name: 'Tasks',
  description: "Today's tasks from the Tasks app.",
  version: '1.0.0',
  defaultSize: { cols: 1, rows: 2 },
  source: { kind: 'mobile-app', appId: 'com.example.tasks', endpoint: '/api/apps/tasks' },
  voiceIntents: ['tasks.add', 'tasks.list'],
};

const Component = () => null;

describe('validateManifest', () => {
  it('accepts a valid manifest', () => {
    expect(validateManifest(manifest)).toEqual([]);
  });

  it('reports every problem at once', () => {
    const problems = validateManifest({
      ...manifest,
      id: 'Bad Id',
      version: 'one',
      source: { kind: 'mobile-app', appId: ' ', endpoint: 'https://elsewhere' },
      voiceIntents: ['add'],
    });
    expect(problems).toHaveLength(5);
  });
});

describe('defineWidget', () => {
  it('freezes the definition', () => {
    const widget = defineWidget({ manifest, component: Component });
    expect(Object.isFrozen(widget)).toBe(true);
    expect(Object.isFrozen(widget.manifest)).toBe(true);
  });

  it('throws on an invalid manifest', () => {
    expect(() =>
      defineWidget({ manifest: { ...manifest, name: '' }, component: Component }),
    ).toThrow(WidgetDefinitionError);
  });
});

describe('WidgetRegistry', () => {
  it('registers, looks up and lists widgets in order', () => {
    const a = defineWidget({ manifest, component: Component });
    const b = defineWidget({ manifest: { ...manifest, id: 'clock' }, component: Component });
    const registry = new WidgetRegistry().register(a).register(b);
    expect(registry.get('clock')).toBe(b);
    expect(registry.list()).toEqual([a, b]);
  });

  it('rejects duplicate ids', () => {
    const widget = defineWidget({ manifest, component: Component });
    const registry = new WidgetRegistry().register(widget);
    expect(() => registry.register(widget)).toThrow(/already registered/);
  });
});
