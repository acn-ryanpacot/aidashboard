import { describe, expect, it } from 'vitest';

import { dueLabel, dueTone, dueTotal, formatDueDate, formatMoney } from './money';

describe('formatMoney', () => {
  it('shows centavos only when there are any', () => {
    expect(formatMoney(182400)).toBe('₱182,400');
    expect(formatMoney(3210.5)).toBe('₱3,210.50');
    expect(formatMoney(12, '$')).toBe('$12');
    expect(formatMoney(-75)).toBe('−₱75');
  });
});

describe('due dates', () => {
  it('labels days from today', () => {
    expect(dueLabel(0)).toBe('today');
    expect(dueLabel(1)).toBe('tomorrow');
    expect(dueLabel(4)).toBe('in 4 days');
    expect(dueLabel(-1)).toBe('1 day late');
    expect(dueLabel(-3)).toBe('3 days late');
  });

  it('colours overdue, inside the reminder window, and later', () => {
    expect(dueTone(-1, 3)).toBe('overdue');
    expect(dueTone(3, 3)).toBe('soon');
    expect(dueTone(4, 3)).toBe('later');
    expect(dueTone(1, 0)).toBe('soon'); // tomorrow stands out even with reminders off
  });

  it('formats a local date without shifting the day', () => {
    expect(formatDueDate('2026-11-18')).toBe('Wed 18 Nov');
  });

  it('adds up what is due within a window, overdue included', () => {
    const payments = [
      { days: -2, amount: 450 },
      { days: 2, amount: 5000 },
      { days: 4, amount: 3210.5 },
      { days: 9, amount: 1400 },
      { days: 1, amount: null },
    ];
    expect(dueTotal(payments, 7)).toBe(8660.5);
  });
});
