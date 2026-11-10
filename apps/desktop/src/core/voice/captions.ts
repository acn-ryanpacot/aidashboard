/**
 * Pure helpers for karaoke-style captions.
 *
 * @module
 */
import type { WordTiming } from './protocol';

/**
 * Find the word being spoken at `elapsed` seconds into a segment.
 *
 * @param words - Word timings in chronological order.
 * @param elapsed - Seconds since the segment started playing.
 * @returns Index of the current word; `-1` before the first word starts. After
 *   the last word ends, the last index is returned so the caption stays lit.
 */
export function activeWordIndex(words: readonly WordTiming[], elapsed: number): number {
  let low = 0;
  let high = words.length - 1;
  let found = -1;
  while (low <= high) {
    const mid = (low + high) >> 1;
    const word = words[mid];
    if (word && word.start <= elapsed) {
      found = mid;
      low = mid + 1;
    } else {
      high = mid - 1;
    }
  }
  return found;
}

/**
 * Smoothly map an RMS-like audio level (0…1) to a perceptual intensity
 * (0…1) — quiet speech still moves the visualiser, loud speech doesn't clip.
 */
export function perceptualLevel(level: number, gain = 4): number {
  const clamped = Math.max(0, Math.min(1, level));
  return 1 - Math.exp(-gain * clamped);
}
