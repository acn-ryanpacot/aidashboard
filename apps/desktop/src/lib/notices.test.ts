import { describe, expect, it } from 'vitest';

import { groupByDayLabel, noticeLabel } from './notices';

describe('notice labels', () => {
  it('names each kind of announcement', () => {
    expect(noticeLabel('timer')).toBe('Timer');
    expect(noticeLabel('alert')).toBe('Stock alert');
    expect(noticeLabel('briefing')).toBe('Briefing');
    expect(noticeLabel('reminder')).toBe('Reminder');
    expect(noticeLabel('app-push')).toBe('Notice');
    expect(noticeLabel(undefined)).toBe('Notice');
  });
});

describe('groupByDayLabel', () => {
  it('groups newest-first items under Today, Yesterday and a date', () => {
    const now = new Date(2026, 10, 11, 18, 0);
    const at = (d: number, h: number) => ({
      created_at: new Date(2026, 10, d, h, 0).toISOString(),
    });
    const items = [at(11, 17), at(11, 9), at(10, 22), at(8, 12)];
    const groups = groupByDayLabel(items, now);
    expect(groups.map((g) => g.label).slice(0, 2)).toEqual(['Today', 'Yesterday']);
    expect(groups.map((g) => g.items.length)).toEqual([2, 1, 1]);
    expect(groups[2]?.label).toMatch(/8/);
  });

  it('handles an empty history', () => {
    expect(groupByDayLabel([])).toEqual([]);
  });
});
