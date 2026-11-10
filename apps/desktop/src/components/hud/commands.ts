/**
 * Commands offered by the palette (Ctrl/⌘ + K). Pure data + a scorer, so the
 * filtering logic is unit-testable.
 *
 * @module
 */

/** One palette entry. */
export interface Command {
  readonly id: string;
  readonly title: string;
  readonly hint?: string;
  readonly keywords?: string;
  readonly run: () => void;
}

/**
 * Rank commands for a query: every query word must appear in the title or
 * keywords; earlier matches in the title score higher.
 */
export function rankCommands(commands: readonly Command[], query: string): Command[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) return [...commands];
  const scored: { command: Command; score: number }[] = [];
  for (const command of commands) {
    const title = command.title.toLowerCase();
    const haystack = `${title} ${command.keywords ?? ''}`.toLowerCase();
    if (!words.every((w) => haystack.includes(w))) continue;
    const position = title.indexOf(words[0] ?? '');
    scored.push({ command, score: position === -1 ? 100 : position });
  }
  return scored.sort((a, b) => a.score - b.score).map((s) => s.command);
}
