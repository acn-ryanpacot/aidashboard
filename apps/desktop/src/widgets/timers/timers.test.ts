import { describe, expect, it } from 'vitest';

import { EARCON_TONES, earconForNotification } from '../../core/audio/earcons';
import { formatCountdown, timerProgress } from '../../lib/format';
import { addNotice } from '../../state/conversation';
import timers from './index';

describe('timer formatting', () => {
  it('formats a countdown', () => {
    expect(formatCountdown(582)).toBe('9:42');
    expect(formatCountdown(3725)).toBe('1:02:05');
    expect(formatCountdown(5)).toBe('0:05');
    expect(formatCountdown(-3)).toBe('0:00');
  });

  it('formats a duration in words', () => {
    expect(formatCountdown(600, { words: true })).toBe('10 min');
    expect(formatCountdown(5400, { words: true })).toBe('1 h 30 min');
    expect(formatCountdown(45, { words: true })).toBe('45 s');
  });

  it('tracks progress from start to finish', () => {
    const now = Date.parse('2026-11-11T10:00:00Z');
    const timer = { duration_s: 600, ends_at: '2026-11-11T10:05:00Z' };
    expect(timerProgress(timer, now)).toBeCloseTo(0.5);
    expect(timerProgress(timer, now - 300_000)).toBe(0);
    expect(timerProgress(timer, now + 600_000)).toBe(1);
  });
});

describe('notification sounds', () => {
  it('rings timers even when chimes are muted', () => {
    expect(earconForNotification('timer')).toEqual({ earcon: 'timer', always: true });
    expect(earconForNotification('alert')).toEqual({ earcon: 'notify', always: false });
    expect(earconForNotification('reminder')).toEqual({ earcon: 'notify', always: false });
    expect(EARCON_TONES.timer).toHaveLength(6);
  });
});

describe('announcements in the transcript', () => {
  it('keep the kind the core sent', () => {
    const [entry] = addNotice([], 'timer', 'Ryan, the rice timer is done.');
    expect(entry).toMatchObject({ speaker: 'notice', kind: 'timer', streaming: false });
  });
});

describe('timers widget manifest', () => {
  it('is a built-in widget', () => {
    expect(timers.manifest.id).toBe('timers');
    expect(timers.manifest.source).toEqual({ kind: 'builtin' });
  });
});
