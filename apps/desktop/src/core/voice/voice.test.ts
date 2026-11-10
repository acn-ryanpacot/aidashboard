import { describe, expect, it } from 'vitest';

import { activeWordIndex, perceptualLevel } from './captions';
import { parseServerMessage, wakePhrase } from './protocol';

const words = [
  { word: 'How', start: 0, end: 0.2 },
  { word: 'can', start: 0.2, end: 0.35 },
  { word: 'I', start: 0.35, end: 0.45 },
  { word: 'help?', start: 0.45, end: 0.9 },
];

describe('activeWordIndex', () => {
  it.each([
    [-0.1, -1],
    [0, 0],
    [0.25, 1],
    [0.44, 2],
    [0.5, 3],
    [5, 3],
  ])('at %ss is word %i', (elapsed, expected) => {
    expect(activeWordIndex(words, elapsed)).toBe(expected);
  });

  it('handles no words', () => {
    expect(activeWordIndex([], 1)).toBe(-1);
  });
});

describe('perceptualLevel', () => {
  it('is 0 for silence, monotonic and bounded', () => {
    expect(perceptualLevel(0)).toBe(0);
    expect(perceptualLevel(0.2)).toBeGreaterThan(perceptualLevel(0.1));
    expect(perceptualLevel(5)).toBeLessThanOrEqual(1);
    expect(perceptualLevel(-1)).toBe(0);
  });
});

describe('parseServerMessage', () => {
  it('parses known messages', () => {
    expect(parseServerMessage('{"type":"state","state":"listening"}')).toEqual({
      type: 'state',
      state: 'listening',
    });
  });

  it.each(['not json', '42', '{"no":"type"}', '{"type":"from_the_future"}'])(
    'ignores %s',
    (raw) => {
      expect(parseServerMessage(raw)).toBeNull();
    },
  );
});

describe('wakePhrase', () => {
  it.each([
    ['hey_jarvis', 'Hey Jarvis'],
    ['hey_jarvis_v0.1', 'Hey Jarvis'],
    ['C:\\models\\hello_jarvis.onnx', 'Hello Jarvis'],
    ['/home/me/HELLO-JARVIS.tflite', 'Hello Jarvis'],
    [null, null],
  ])('%s → %s', (model, phrase) => {
    expect(wakePhrase(model)).toBe(phrase);
  });
});
