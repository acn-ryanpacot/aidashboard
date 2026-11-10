/**
 * Date/time helpers for the HUD.
 *
 * @module
 */

/** "Good morning" / "Good afternoon" / "Good evening" for a given hour (0–23). */
export function partOfDayGreeting(hour: number): string {
  if (hour >= 5 && hour < 12) return 'Good morning';
  if (hour >= 12 && hour < 18) return 'Good afternoon';
  return 'Good evening';
}

/** Zero-padded two-digit number. */
export const pad2 = (value: number): string => value.toString().padStart(2, '0');
