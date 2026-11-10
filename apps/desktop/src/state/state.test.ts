import { describe, expect, it } from 'vitest';

import { partOfDayGreeting } from '../lib/time';
import { createAssistantStore } from './assistantStore';
import { MAX_ENTRIES, addEntry, appendAssistantDelta, completeAssistantTurn } from './conversation';

describe('conversation reducers', () => {
  it('streams deltas into one assistant entry, then completes it', () => {
    let entries = addEntry([], 'user', 'Status?');
    entries = appendAssistantDelta(entries, 'All ');
    entries = appendAssistantDelta(entries, 'good');
    expect(entries).toHaveLength(2);
    expect(entries[1]).toMatchObject({ speaker: 'assistant', text: 'All good', streaming: true });

    entries = completeAssistantTurn(entries, 'All good.');
    expect(entries[1]).toMatchObject({ text: 'All good.', streaming: false });
  });

  it('completing without a streaming entry adds a new one', () => {
    const entries = completeAssistantTurn([], 'How can I help you Ryan?');
    expect(entries).toEqual([expect.objectContaining({ speaker: 'assistant', streaming: false })]);
  });

  it('caps the transcript length', () => {
    let entries = addEntry([], 'user', '0');
    for (let i = 1; i <= MAX_ENTRIES + 5; i++) entries = addEntry(entries, 'user', String(i));
    expect(entries).toHaveLength(MAX_ENTRIES);
    expect(entries.at(-1)?.text).toBe(String(MAX_ENTRIES + 5));
  });
});

describe('assistant store', () => {
  it('falls back to idle when the link drops', () => {
    const store = createAssistantStore();
    store.getState().setConnection('online');
    store.getState().setState('speaking');
    store.getState().setConnection('offline');
    expect(store.getState().state).toBe('idle');
  });
});

describe('partOfDayGreeting', () => {
  it.each([
    [4, 'Good evening'],
    [5, 'Good morning'],
    [12, 'Good afternoon'],
    [18, 'Good evening'],
  ])('%i:00 → %s', (hour, greeting) => {
    expect(partOfDayGreeting(hour)).toBe(greeting);
  });
});
