import { describe, expect, it } from 'vitest';

import type { DocumentsStatus } from '../core/api/client';
import { describeKinds, documentsSummary, webSummary } from './knowledge';

const docs = (patch: Partial<DocumentsStatus> = {}): DocumentsStatus => ({
  available: true,
  folder: 'C:/Users/ryan/Documents/Jarvis',
  exists: true,
  indexing: false,
  total: 5,
  indexed: 4,
  by_kind: { pdf: 2, spreadsheet: 2, word: 1 },
  files: [],
  last_indexed: null,
  error: null,
  ...patch,
});

describe('describeKinds', () => {
  it('pluralises and orders the most common kinds first', () => {
    expect(describeKinds({ word: 1, pdf: 12, text: 0, spreadsheet: 3 })).toBe(
      '12 PDFs, 3 spreadsheets, 1 Word file',
    );
    expect(describeKinds({ spreadsheet: 1, pdf: 1 })).toBe('1 PDF, 1 spreadsheet');
  });
});

describe('documentsSummary', () => {
  it('explains every state of the folder', () => {
    expect(documentsSummary(docs({ folder: '' }))).toBe('No folder chosen yet.');
    expect(documentsSummary(docs({ exists: false }))).toMatch(/doesn’t exist/);
    expect(documentsSummary(docs({ total: 0, by_kind: {} }))).toMatch(/no files/);
    expect(documentsSummary(docs({ indexing: true }))).toBe(
      'Reading 5 files (2 PDFs, 2 spreadsheets, 1 Word file)…',
    );
    expect(documentsSummary(docs())).toBe(
      '4 of 5 files ready (2 PDFs, 2 spreadsheets, 1 Word file); 1 couldn’t be read.',
    );
    expect(documentsSummary(docs({ indexed: 5 }))).toMatch(/^5 of 5 files ready .*\.$/);
    expect(documentsSummary(docs({ indexed: 0, error: 'No embedding model.' }))).toBe(
      '0 of 5 files ready (2 PDFs, 2 spreadsheets, 1 Word file).',
    );
    expect(documentsSummary(docs({ available: false, error: 'No embeddings.' }))).toBe(
      'No embeddings.',
    );
  });
});

describe('webSummary', () => {
  const web = { enabled: true, provider: 'DuckDuckGo', mode: 'auto', searxng: false } as const;

  it('recommends SearXNG when only DuckDuckGo is available', () => {
    const summary = webSummary({ ...web, reads_pages: true });
    expect(summary.title).toBe('DuckDuckGo');
    expect(summary.hint).toMatch(/SearXNG/);
  });

  it('reports SearXNG and the off state', () => {
    expect(
      webSummary({ ...web, provider: 'SearXNG, then DuckDuckGo', searxng: true, reads_pages: true })
        .title,
    ).toBe('SearXNG, then DuckDuckGo');
    expect(webSummary({ ...web, enabled: false, mode: 'off', reads_pages: true }).title).toBe(
      'Off',
    );
  });
});
