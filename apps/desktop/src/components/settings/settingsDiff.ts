import type { RuntimeSettings } from '../../core/api/client';

/**
 * The fields of `draft` that differ from `saved` — what to send in a PUT.
 * Arrays are compared by value.
 */
export function diffSettings(
  saved: RuntimeSettings,
  draft: RuntimeSettings,
): Partial<RuntimeSettings> {
  const patch: Record<string, unknown> = {};
  for (const key of Object.keys(draft) as (keyof RuntimeSettings)[]) {
    const before = saved[key];
    const after = draft[key];
    const same =
      Array.isArray(before) && Array.isArray(after)
        ? before.length === after.length && before.every((v, i) => v === after[i])
        : before === after;
    if (!same) patch[key] = after;
  }
  return patch as Partial<RuntimeSettings>;
}
