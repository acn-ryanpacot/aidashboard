import { describe, expect, it } from 'vitest';

import { rankCommands } from '../components/hud/commands';
import { diffSettings } from '../components/settings/settingsDiff';
import { formatUptime, groupByDay, headlineAge } from '../lib/format';
import {
  DEFAULT_LAYOUT,
  type DashboardLayout,
  addWidget,
  findWidget,
  moveWidget,
  normalizeLayout,
  placedIds,
  removeWidget,
  resizeWidget,
} from '../state/layout';
import type { RuntimeSettings } from './api/client';
import { EchoGate, FrameRing, floatRms, pcm16Rms } from './audio/echoGate';

const KNOWN = new Set([
  'clock',
  'weather',
  'schedule',
  'conversation',
  'tasks',
  'news',
  'memories',
  'system',
]);

describe('layout reducers', () => {
  it('moves a widget across zones and within a zone', () => {
    let layout: DashboardLayout = moveWidget(DEFAULT_LAYOUT, 'news', 'left', 0);
    expect(layout.zones.left.map((p) => p.id)).toEqual(['news', 'clock', 'weather', 'schedule']);
    expect(layout.zones.right.map((p) => p.id)).toEqual(['conversation', 'tasks']);
    layout = moveWidget(layout, 'news', 'left', 99);
    expect(findWidget(layout, 'news')).toEqual({ zone: 'left', index: 3 });
    expect(moveWidget(layout, 'missing', 'left', 0)).toBe(layout);
  });

  it('resizes within 1–4 rows', () => {
    const grown = resizeWidget(resizeWidget(DEFAULT_LAYOUT, 'clock', 5), 'clock', 1);
    expect(grown.zones.left[0]?.rows).toBe(4);
    expect(resizeWidget(DEFAULT_LAYOUT, 'clock', -9).zones.left[0]?.rows).toBe(1);
  });

  it('adds once and removes', () => {
    const added = addWidget(DEFAULT_LAYOUT, 'system', 'left', 2);
    expect(placedIds(added).has('system')).toBe(true);
    expect(addWidget(added, 'system', 'right', 2)).toBe(added);
    expect(placedIds(removeWidget(added, 'system')).has('system')).toBe(false);
  });

  it('normalises untrusted stored layouts', () => {
    expect(normalizeLayout(null, KNOWN)).toBe(DEFAULT_LAYOUT);
    expect(normalizeLayout({ zones: 'nope' }, KNOWN)).toBe(DEFAULT_LAYOUT);
    const cleaned = normalizeLayout(
      {
        zones: {
          left: [{ id: 'clock', rows: 9 }, { id: 'ghost', rows: 2 }, { id: 'clock', rows: 1 }, 'x'],
          right: [{ id: 'news' }],
        },
      },
      KNOWN,
    );
    expect(cleaned.zones).toEqual({
      left: [{ id: 'clock', rows: 4 }],
      right: [{ id: 'news', rows: 2 }],
    });
  });
});

describe('EchoGate', () => {
  it('ignores the echo of Jarvis but catches the user talking over it', () => {
    const gate = new EchoGate({ minSpeechFrames: 3 });
    // Jarvis speaking: mic hears ~30% of the output. Gate learns the leak.
    for (let i = 0; i < 40; i++) expect(gate.push(0.06, 0.2)).toBe(false);
    expect(gate.leak).toBeGreaterThan(0.2);
    expect(gate.leak).toBeLessThan(0.4);
    // User talks clearly above the echo for three frames → barge-in.
    expect(gate.push(0.3, 0.2)).toBe(false);
    expect(gate.push(0.3, 0.2)).toBe(false);
    expect(gate.push(0.3, 0.2)).toBe(true);
  });

  it('needs sustained speech, not a blip', () => {
    const gate = new EchoGate({ minSpeechFrames: 3 });
    for (let i = 0; i < 10; i++) gate.push(0.003, 0); // quiet room
    expect(gate.push(0.2, 0)).toBe(false);
    expect(gate.push(0.002, 0)).toBe(false); // streak broken
    expect(gate.push(0.2, 0)).toBe(false);
    expect(gate.push(0.2, 0)).toBe(false);
    expect(gate.push(0.2, 0)).toBe(true);
  });

  it('measures levels', () => {
    expect(pcm16Rms(new Int16Array([16384, -16384]))).toBeCloseTo(0.5);
    expect(floatRms(new Float32Array([0.5, -0.5]))).toBeCloseTo(0.5);
    expect(pcm16Rms(new Int16Array(0))).toBe(0);
  });

  it('frame ring keeps only the newest frames', () => {
    const ring = new FrameRing(2);
    [1, 2, 3].forEach((n) => ring.push(new ArrayBuffer(n)));
    expect(ring.drain().map((b) => b.byteLength)).toEqual([2, 3]);
    expect(ring.drain()).toEqual([]);
  });
});

describe('command palette ranking', () => {
  const run = () => undefined;
  const commands = [
    { id: 'a', title: 'Edit layout', keywords: 'widgets arrange', run },
    { id: 'b', title: 'Theme: Stealth', keywords: 'appearance', run },
    { id: 'c', title: 'Morning briefing', keywords: 'brief day', run },
  ];
  it('filters by every word and prefers title matches', () => {
    expect(rankCommands(commands, '').map((c) => c.id)).toEqual(['a', 'b', 'c']);
    expect(rankCommands(commands, 'brief').map((c) => c.id)).toEqual(['c']);
    expect(rankCommands(commands, 'widgets').map((c) => c.id)).toEqual(['a']);
    expect(rankCommands(commands, 'theme stealth').map((c) => c.id)).toEqual(['b']);
    expect(rankCommands(commands, 'zzz')).toEqual([]);
  });
});

describe('settings diff', () => {
  const base = {
    user_name: 'Ryan',
    tts_speed: 1,
    news_feeds: ['https://a'],
  } as unknown as RuntimeSettings;
  it('sends only changed fields, comparing arrays by value', () => {
    expect(diffSettings(base, { ...base })).toEqual({});
    expect(diffSettings(base, { ...base, news_feeds: ['https://a'] })).toEqual({});
    expect(diffSettings(base, { ...base, user_name: 'Tony', news_feeds: [] })).toEqual({
      user_name: 'Tony',
      news_feeds: [],
    });
  });
});

describe('widget formatting', () => {
  const now = new Date(2026, 10, 10, 12, 0);
  it('headline ages', () => {
    expect(headlineAge(null, now)).toBe('');
    expect(headlineAge(new Date(2026, 10, 10, 11, 25).toISOString(), now)).toBe('35m');
    expect(headlineAge(new Date(2026, 10, 10, 9, 0).toISOString(), now)).toBe('3h');
    expect(headlineAge(new Date(2026, 10, 6, 12, 0).toISOString(), now)).toBe('4d');
  });

  it('groups events by day', () => {
    const event = (day: number, hour: number) => ({
      title: `e${day}`,
      start: new Date(2026, 10, day, hour).toISOString(),
      end: new Date(2026, 10, day, hour + 1).toISOString(),
      all_day: false,
      location: '',
      calendar: '',
    });
    expect(groupByDay([event(10, 9), event(11, 9), event(13, 9)], now).map((g) => g.label)).toEqual(
      ['Today', 'Tomorrow', 'Later'],
    );
  });

  it('uptime', () => {
    expect(formatUptime(65 * 60)).toBe('1h 5m');
    expect(formatUptime(3 * 86400 + 4 * 3600)).toBe('3d 4h');
    expect(formatUptime(30)).toBe('0m');
  });
});
