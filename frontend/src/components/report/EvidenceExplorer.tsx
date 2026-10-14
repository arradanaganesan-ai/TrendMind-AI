import { useMemo, useState } from 'react';
import { SearchX } from 'lucide-react';
import { CitationList } from './CitationLink';
import type { EvidenceClass, ResearchReport, SourceRef } from '../../types/api';

/**
 * Evidence Explorer (4C) — browse the report's evidence both ways:
 *   • By source: every collected source, its retrieval state, and the exact
 *     texts in this report that cite it.
 *   • By claim: every claim/finding with its citations; claims with NO
 *     supporting source are flagged instead of silently shown.
 * Everything is computed from the stored report — no estimates.
 */

type ClaimKind = 'finding' | 'comparison' | 'conflict' | 'development' | 'opportunity';

interface ExplorableView {
  kind: ClaimKind;
  label: string;
  text: string;
  sourceIds: string[];
  evidenceClass?: EvidenceClass;
}

const KIND_LABELS: Record<Exclude<ClaimKind, 'finding'>, string> = {
  comparison: 'Evidence comparison',
  conflict: 'Conflicting position',
  development: 'Emerging development',
  opportunity: 'Opportunity',
};

const EVIDENCE_META: Record<EvidenceClass, { label: string; className: string }> = {
  fact: { label: 'Retrieved information', className: 'badge-live' },
  interpretation: { label: 'AI interpretation', className: 'badge-neutral' },
  hypothesis: {
    label: 'Hypothesis — needs verification',
    className: 'badge bg-amber-400/10 text-amber-300 border-amber-400/30',
  },
};

function collectClaims(report: ResearchReport): ExplorableView[] {
  const claims: ExplorableView[] = [];
  for (const f of report.keyFindings) {
    claims.push({ kind: 'finding', label: 'Key finding', text: f.text, sourceIds: f.sourceIds, evidenceClass: f.evidenceClass });
  }
  for (const c of report.evidenceComparison) {
    for (const cl of c.claims) {
      claims.push({ kind: 'comparison', label: KIND_LABELS.comparison, text: cl.claim, sourceIds: cl.sourceIds });
    }
  }
  for (const c of report.conflictingClaims) {
    for (const p of c.positions) {
      claims.push({ kind: 'conflict', label: KIND_LABELS.conflict, text: p.position, sourceIds: p.sourceIds });
    }
  }
  for (const f of report.emergingDevelopments) {
    claims.push({ kind: 'development', label: KIND_LABELS.development, text: f.text, sourceIds: f.sourceIds });
  }
  for (const f of report.opportunities) {
    claims.push({ kind: 'opportunity', label: KIND_LABELS.opportunity, text: f.text, sourceIds: f.sourceIds });
  }
  return claims;
}

export default function EvidenceExplorer({ report }: { report: ResearchReport }) {
  const [view, setView] = useState<'source' | 'claim'>('source');
  const [filter, setFilter] = useState('');

  const claims = useMemo(() => collectClaims(report), [report]);
  const uncited = useMemo(() => claims.filter((c) => c.sourceIds.length === 0), [claims]);

  const citingById = useMemo(() => {
    const map = new Map<string, ExplorableView[]>();
    for (const claim of claims) {
      for (const sid of claim.sourceIds) {
        const list = map.get(sid) ?? [];
        list.push(claim);
        map.set(sid, list);
      }
    }
    return map;
  }, [claims]);

  const citedSourceIds = useMemo(() => new Set(report.sources.flatMap((s) => [s.id])), [report.sources]);
  const neverCited = useMemo(
    () => report.sources.filter((s) => !(citingById.get(s.id)?.length)),
    [report.sources, citingById],
  );

  const q = filter.trim().toLowerCase();
  const sources: SourceRef[] = q
    ? report.sources.filter(
        (s) =>
          s.title.toLowerCase().includes(q) ||
          s.domain.toLowerCase().includes(q) ||
          s.id.toLowerCase().includes(q) ||
          s.snippet.toLowerCase().includes(q),
      )
    : report.sources;
  const filteredClaims = q
    ? claims.filter((c) => c.text.toLowerCase().includes(q))
    : claims;

  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex rounded-md border border-slateui-600/70 p-0.5" role="tablist" aria-label="Evidence explorer view">
          <button
            type="button"
            role="tab"
            aria-selected={view === 'source'}
            onClick={() => setView('source')}
            className={`rounded px-3 py-1.5 text-xs transition-colors ${
              view === 'source' ? 'bg-violetui-600/20 text-violetui-300' : 'text-slateui-400 hover:text-slateui-200'
            }`}
          >
            By source
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={view === 'claim'}
            onClick={() => setView('claim')}
            className={`rounded px-3 py-1.5 text-xs transition-colors ${
              view === 'claim' ? 'bg-violetui-600/20 text-violetui-300' : 'text-slateui-400 hover:text-slateui-200'
            }`}
          >
            By claim
          </button>
        </div>
        <label className="flex min-w-[220px] flex-1 items-center gap-2 rounded-md border border-slateui-600/70 bg-midnight-800 px-3 py-1.5">
          <span className="sr-only">Filter evidence</span>
          <input
            type="search"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder={
              view === 'source'
                ? 'Filter by source id, title, or domain…'
                : 'Filter claims by text…'
            }
            className="min-w-0 flex-1 bg-transparent text-xs text-slateui-100 placeholder:text-slateui-500 focus:outline-none"
          />
        </label>
        <p className="text-2xs text-slateui-500">
          {claims.length} claims · {uncited.length} uncited · {neverCited.length} of{' '}
          {citedSourceIds.size + neverCited.length} sources never cited
        </p>
      </div>

      {view === 'source' ? (
        sources.length === 0 ? (
          <div className="panel flex items-center gap-3 p-5 text-sm text-slateui-400">
            <SearchX size={18} aria-hidden className="text-slateui-500" />
            No source matches “{filter}”.
          </div>
        ) : (
          <ul className="space-y-2">
            {sources.map((s) => {
              const citing = citingById.get(s.id) ?? [];
              return (
                <li key={s.id}>
                  <details className="panel group p-4">
                    <summary className="flex cursor-pointer list-none flex-wrap items-center gap-3 [&::-webkit-details-marker]:hidden">
                      <span className="font-mono text-xs font-semibold text-violetui-400">{s.id}</span>
                      <span className="min-w-0 flex-1 truncate text-sm font-medium text-slateui-100">
                        {s.title}
                      </span>
                      <span className="text-2xs text-slateui-500">{s.domain}</span>
                      <span
                        className={`badge ${
                          s.extractionStatus === 'extracted'
                            ? 'badge-live'
                            : s.extractionStatus === 'blocked' || s.extractionStatus === 'failed'
                              ? 'bg-amber-400/10 text-amber-300 border-amber-400/30'
                              : 'badge-neutral'
                        }`}
                      >
                        {s.extractionStatus.replace('_', ' ')}
                      </span>
                      <span className="text-2xs tabular-nums text-slateui-400">
                        {citing.length} citing {citing.length === 1 ? 'claim' : 'claims'}
                      </span>
                    </summary>
                    <div className="mt-3 border-t border-slateui-700/50 pt-3">
                      <p className="mb-2 text-2xs leading-relaxed text-slateui-500">
                        Snippet: {s.snippet}
                        {s.extractionNote ? ` · Retrieval note: ${s.extractionNote}` : ''}
                      </p>
                      {citing.length > 0 ? (
                        <ul className="space-y-1.5">
                          {citing.map((c, i) => (
                            <li key={i} className="flex gap-2 text-xs leading-relaxed text-slateui-300">
                              <span className="shrink-0 text-2xs uppercase tracking-wider text-slateui-500">
                                {c.kind}
                              </span>
                              <span>{c.text}</span>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="text-xs text-amber-300/90">
                          No claim in this report cites this source — it was collected but not used.
                        </p>
                      )}
                    </div>
                  </details>
                </li>
              );
            })}
          </ul>
        )
      ) : filteredClaims.length === 0 ? (
        <div className="panel flex items-center gap-3 p-5 text-sm text-slateui-400">
          <SearchX size={18} aria-hidden className="text-slateui-500" />
          No claim matches “{filter}”.
        </div>
      ) : (
        <ul className="space-y-2">
          {filteredClaims.map((c, i) => (
            <li key={i} className="panel p-4">
              <div className="mb-1.5 flex flex-wrap items-center gap-2">
                {c.evidenceClass ? (
                  <span className={EVIDENCE_META[c.evidenceClass].className}>
                    {EVIDENCE_META[c.evidenceClass].label}
                  </span>
                ) : (
                  <span className="badge-neutral">{c.label}</span>
                )}
                {c.sourceIds.length === 0 && (
                  <span
                    className="badge bg-amber-400/10 text-amber-300 border-amber-400/30"
                    title="This claim was not tied to any collected source."
                  >
                    No supporting source
                  </span>
                )}
              </div>
              <p className="text-sm leading-relaxed text-slateui-200">
                {c.text}
                {c.sourceIds.length > 0 && <CitationList sourceIds={c.sourceIds} sources={report.sources} />}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
