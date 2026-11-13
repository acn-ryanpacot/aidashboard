import { FileWarning, Globe, LoaderCircle, RefreshCw } from 'lucide-react';
import { useState } from 'react';

import { type KnowledgeStatus as Knowledge, coreApi } from '../../core/api/client';
import { useCoreData } from '../../core/api/useCoreData';
import { cn } from '../../lib/cn';
import { relativeAgo } from '../../lib/format';
import { documentsSummary, webSummary } from '../../lib/knowledge';

/** Files with a problem shown before "and N more". */
const PROBLEMS_SHOWN = 4;

/**
 * Settings → Knowledge, below the folder field: what Jarvis has read from
 * the documents folder (refreshing live while it indexes), a Re-index
 * button, and which web search he uses.
 *
 * @param props.editable - Show the Re-index button (this PC only).
 */
export function KnowledgeStatus({ editable }: { editable: boolean }) {
  const { data, reload } = useCoreData<Knowledge>(['documents', 'settings'], coreApi.getKnowledge);
  const [busy, setBusy] = useState(false);

  if (!data) return null;
  const docs = data.documents;
  const problems = docs.files.filter((f) => f.problem);
  const web = webSummary(data.web);

  const reindex = async () => {
    setBusy(true);
    await coreApi.reindexDocuments().catch(() => undefined);
    setBusy(false);
    reload();
  };

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-white/8 bg-white/[0.02] p-3">
        <div className="flex items-start gap-2.5">
          {docs.indexing ? (
            <LoaderCircle className="mt-0.5 size-3.5 shrink-0 animate-spin text-arc-300" />
          ) : (
            <span
              className={cn(
                'mt-1.5 size-1.5 shrink-0 rounded-full',
                docs.indexed > 0 ? 'bg-signal-green' : 'bg-white/25',
              )}
            />
          )}
          <div className="min-w-0 flex-1">
            <p className="text-[12.5px] text-white/75" data-testid="documents-summary">
              {documentsSummary(docs)}
            </p>
            {docs.error && docs.available && (
              <p className="mt-1 text-[11.5px] text-amber-300/80">
                {docs.error}
                {!docs.error.includes('ollama pull') && (
                  <>
                    {' '}
                    Run <code className="font-mono">ollama pull nomic-embed-text</code>.
                  </>
                )}
              </p>
            )}
            {docs.last_indexed && !docs.indexing && docs.folder && (
              <p className="mt-0.5 font-mono text-[10px] text-white/30">
                checked {relativeAgo(docs.last_indexed)} · new files are picked up every few minutes
              </p>
            )}
          </div>
          {editable && docs.available && docs.folder && docs.exists && (
            <button
              type="button"
              onClick={() => void reindex()}
              disabled={busy || docs.indexing}
              className="flex shrink-0 items-center gap-1.5 rounded-lg border border-white/10 px-2.5 py-1 text-[11.5px] text-white/65 transition hover:border-arc-400/40 hover:text-white disabled:opacity-40"
            >
              <RefreshCw className={cn('size-3', (busy || docs.indexing) && 'animate-spin')} />
              Re-index now
            </button>
          )}
        </div>
        {problems.length > 0 && (
          <ul className="mt-2.5 space-y-1 border-t border-white/6 pt-2.5">
            {problems.slice(0, PROBLEMS_SHOWN).map((file) => (
              <li key={file.path} className="flex items-start gap-2 text-[11.5px] text-white/45">
                <FileWarning className="mt-0.5 size-3 shrink-0 text-amber-300/70" />
                <span className="min-w-0">
                  <span className="font-mono text-white/60">{file.path}</span>: {file.problem}
                </span>
              </li>
            ))}
            {problems.length > PROBLEMS_SHOWN && (
              <li className="pl-5 text-[11px] text-white/30">
                and {problems.length - PROBLEMS_SHOWN} more
              </li>
            )}
          </ul>
        )}
      </div>

      <div className="flex items-start gap-2.5">
        <Globe className="mt-0.5 size-3.5 shrink-0 text-arc-300/70" />
        <div className="min-w-0">
          <p className="text-[12.5px] text-white/75">
            Web search: <span className="text-white/90">{web.title}</span>
          </p>
          <p className="mt-0.5 text-[11.5px] leading-relaxed text-white/35">{web.hint}</p>
        </div>
      </div>
    </div>
  );
}
