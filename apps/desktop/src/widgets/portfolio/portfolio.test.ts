import { describe, expect, it } from 'vitest';

import {
  formatPercent,
  formatPesos,
  formatSession,
  formatTradingDate,
  moveColor,
} from '../../lib/format';
import portfolio from './index';

describe('portfolio formatting', () => {
  it('formats pesos, signed and unsigned', () => {
    expect(formatPesos(101_500)).toBe('₱101,500');
    expect(formatPesos(1_500, { signed: true })).toBe('+₱1,500');
    expect(formatPesos(-202.51, { signed: true })).toBe('−₱203');
    expect(formatPesos(0, { signed: true })).toBe('₱0');
    expect(formatPesos(306, { decimals: 2 })).toBe('₱306.00');
    expect(formatPesos(0.0042)).toBe('₱0.0042'); // penny stocks keep their ticks
  });

  it('formats percentages with a true minus sign', () => {
    expect(formatPercent(1.5)).toBe('+1.50%');
    expect(formatPercent(-0.482)).toBe('−0.48%');
    expect(formatPercent(6.84, 1)).toBe('+6.8%');
    expect(formatPercent(0)).toBe('0.00%');
    expect(formatPercent(null)).toBe('—');
  });

  it('colours gains and losses', () => {
    expect(moveColor(3)).toBe('text-signal-green');
    expect(moveColor(-3)).toBe('text-signal-red');
    expect(moveColor(0)).toBe('text-white/55');
    expect(moveColor(null)).toBe('text-white/55');
  });

  it('labels the trading session as a calendar date', () => {
    const label = formatTradingDate('2026-11-10');
    expect(label).toMatch(/10/);
    expect(label).toMatch(/Nov/);
    expect(formatSession('2026-11-10', true)).toBe(`Today · ${label}`);
    expect(formatSession('2026-11-10', false)).toBe(`Last session · ${label}`);
    expect(formatSession(null, false)).toBe('Last sync');
    expect(formatTradingDate(null)).toBe('');
  });
});

describe('portfolio widget manifest', () => {
  it('is a mobile-app widget backed by the core proxy', () => {
    expect(portfolio.manifest.source).toEqual({
      kind: 'mobile-app',
      appId: 'com.pisotiyempo',
      endpoint: '/api/apps/pisotiyempo',
    });
  });
});
