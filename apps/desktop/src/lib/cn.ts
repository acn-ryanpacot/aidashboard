/**
 * Join class names, skipping falsy values.
 *
 * @example
 * ```ts
 * cn('a', isActive && 'b', undefined); // "a b" when isActive
 * ```
 */
export function cn(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(' ');
}
