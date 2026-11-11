import { describe, expect, it } from 'vitest';

import { createAssistantStore } from '../state/assistantStore';
import { formatLatency } from '../lib/format';
import { relativeTime } from './api/client';
import { EARCON_TONES, earconForTransition } from './audio/earcons';
import { parseServerMessage } from './voice/protocol';
import { isPushToTalkChord } from './voice/usePushToTalk';
import { wantsAudio } from './voice/VoiceAssistant';

describe('earconForTransition', () => {
  it.each([
    ['idle', 'listening', 'wake'],
    ['speaking', 'listening', 'wake'],
    ['listening', 'thinking', 'listen-end'],
    ['thinking', 'speaking', null],
    ['listening', 'listening', null],
  ])('%s → %s plays %s', (from, to, expected) => {
    expect(earconForTransition(from, to)).toBe(expected);
  });

  it('every earcon is short and quiet', () => {
    for (const [name, tones] of Object.entries(EARCON_TONES)) {
      const end = Math.max(...tones.map((t) => t.at + t.length));
      // The timer chime repeats on purpose so it's heard across the room.
      expect(end).toBeLessThan(name === 'timer' ? 1.5 : 0.6);
      expect(Math.max(...tones.map((t) => t.gain))).toBeLessThanOrEqual(0.08);
    }
  });
});

describe('wantsAudio', () => {
  it.each([
    ['idle', true, 'off', true],
    ['idle', false, 'off', false],
    ['listening', false, 'off', true],
    ['speaking', true, 'wake_word', true],
    ['speaking', false, 'wake_word', false],
    ['thinking', false, 'voice', true],
    ['speaking', true, 'off', false],
  ] as const)('%s / wake=%s / barge=%s → %s', (state, wake, barge, expected) => {
    expect(wantsAudio(state, wake, barge)).toBe(expected);
  });
});

describe('isPushToTalkChord', () => {
  const key = (code: string, ctrlKey = false, metaKey = false, repeat = false) => ({
    code,
    ctrlKey,
    metaKey,
    repeat,
  });
  it('matches Ctrl/⌘ + Space only', () => {
    expect(isPushToTalkChord(key('Space', true))).toBe(true);
    expect(isPushToTalkChord(key('Space', false, true))).toBe(true);
    expect(isPushToTalkChord(key('Space'))).toBe(false);
    expect(isPushToTalkChord(key('KeyK', true))).toBe(false);
    expect(isPushToTalkChord(key('Space', true, false, true))).toBe(false);
  });
});

describe('relativeTime', () => {
  const now = new Date(2026, 10, 10, 14, 0);
  it('phrases near and far times', () => {
    expect(relativeTime(new Date(2026, 10, 10, 14, 0, 20).toISOString(), now)).toBe('now');
    expect(relativeTime(new Date(2026, 10, 10, 14, 12).toISOString(), now)).toBe('in 12 min');
    expect(relativeTime(new Date(2026, 10, 10, 18, 30).toISOString(), now)).toMatch(/^today /);
    expect(relativeTime(new Date(2026, 10, 11, 9, 0).toISOString(), now)).toMatch(/^tomorrow /);
    expect(relativeTime(new Date(2026, 10, 14, 9, 0).toISOString(), now)).not.toMatch(
      /today|tomorrow/,
    );
  });
});

describe('formatLatency', () => {
  it.each([
    [null, '—'],
    [undefined, '—'],
    [320.4, '320 ms'],
    [1840, '1.84 s'],
  ])('%s → %s', (input, expected) => {
    expect(formatLatency(input)).toBe(expected);
  });
});

describe('protocol v2', () => {
  it('accepts the new server messages', () => {
    for (const type of ['interrupted', 'tool', 'metrics', 'enrollment', 'notification']) {
      expect(parseServerMessage(JSON.stringify({ type }))?.type).toBe(type);
    }
  });
});

describe('assistant store (phase 2/3)', () => {
  it('tracks tools, data versions and clears the tool when thinking ends', () => {
    const store = createAssistantStore();
    store.getState().setState('thinking');
    store.getState().setActiveTool('Checking the weather');
    expect(store.getState().activeTool).toBe('Checking the weather');
    store.getState().setState('speaking');
    expect(store.getState().activeTool).toBeNull();

    store.getState().bumpData('tasks');
    store.getState().bumpData('tasks');
    expect(store.getState().dataVersions).toEqual({ tasks: 2 });
  });
});
