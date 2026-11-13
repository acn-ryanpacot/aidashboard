/**
 * Wording for Settings → Knowledge (documents folder and web search).
 *
 * @module
 */
import type { DocumentsStatus, KnowledgeStatus } from '../core/api/client';

const KIND_NAMES: Record<string, [one: string, many: string]> = {
  pdf: ['PDF', 'PDFs'],
  word: ['Word file', 'Word files'],
  spreadsheet: ['spreadsheet', 'spreadsheets'],
  text: ['note', 'notes'],
};
const KIND_ORDER = ['pdf', 'spreadsheet', 'word', 'text'];

/** "12 PDFs, 3 spreadsheets, 1 note" (most common kinds first, then a fixed order). */
export function describeKinds(byKind: Readonly<Record<string, number>>): string {
  return Object.entries(byKind)
    .filter(([, count]) => count > 0)
    .sort(([a, x], [b, y]) => y - x || KIND_ORDER.indexOf(a) - KIND_ORDER.indexOf(b))
    .map(([kind, count]) => {
      const [one, many] = KIND_NAMES[kind] ?? [kind, kind];
      return `${count} ${count === 1 ? one : many}`;
    })
    .join(', ');
}

/** One line about the documents folder for Settings. */
export function documentsSummary(docs: DocumentsStatus): string {
  if (!docs.available) return docs.error ?? 'Document search is unavailable.';
  if (!docs.folder) return 'No folder chosen yet.';
  if (!docs.exists) return 'That folder doesn’t exist.';
  if (docs.total === 0) return 'The folder has no files Jarvis can read yet.';
  const kinds = describeKinds(docs.by_kind);
  const pending = docs.total - docs.indexed;
  if (docs.indexing && pending > 0) return `Reading ${docs.total} files (${kinds})…`;
  const head = `${docs.indexed} of ${docs.total} files ready (${kinds})`;
  // With a general error (no embedding model) the error line explains it instead.
  return pending > 0 && !docs.indexing && !docs.error
    ? `${head}; ${pending} couldn’t be read.`
    : `${head}.`;
}

/** "SearXNG", "DuckDuckGo" or "Off", with what to do next. */
export function webSummary(web: KnowledgeStatus['web']): { title: string; hint: string } {
  if (!web.enabled) {
    return {
      title: 'Off',
      hint: 'Set JARVIS_WEB_SEARCH=auto in services/core/.env and restart the core.',
    };
  }
  if (web.searxng) {
    return {
      title: web.provider,
      hint: 'Private search through your own SearXNG server.',
    };
  }
  return {
    title: web.provider,
    hint: 'Works with no setup, but DuckDuckGo may pause searches if there are too many. SearXNG is more reliable: docs/guides/web-search.md.',
  };
}
