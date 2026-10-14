import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowLeft,
  ArrowLeftRight,
  Download,
  FileDown,
  FileJson,
  GitCompareArrows,
  Globe,
  Info,
} from 'lucide-react';
import EmptyState from '../components/ui/EmptyState';
import ErrorState from '../components/ui/ErrorState';
import { SkeletonList } from '../components/ui/Skeletons';
import ModeBadge from '../components/ui/ModeBadge';
import { useConfigStatus } from '../hooks/useConfigStatus';
import { api, ApiError } from '../services/api';
import type {
  ComparedFindingPair,
  ComparedFindingRef,
  ComparedRun,
  ReportComparison,
  ResearchListItem,
  ResearchRecord,
  SourceRef,
} from '../types/api';

/**
 * Report comparison workspace. Two stored runs are compared by the BACKEND
 * (deterministic text matching, optional AI classification with an honest
 * fallback), and this page renders the returned structure with full
 * transparency: which mode ran, how similarity was computed, and which
 * conflicts still need human review.
 */

function fmtDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

function fmtDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

interface SideState {
  record: ResearchRecord | null;
  loading: boolean;
  error: string | null;
}

function loadRecord(id: string): Promise<SideState> {
  return api
    .getResearch(id)
    .then((record) => ({ record, loading: false, error: null }))
    .catch((err: unknown) => ({
      record: null,
      loading: false,
      error: err instanceof ApiError ? err.message : 'Could not load this record.',
    }));
}

type SourceMap = Map<string, SourceRef>;

function toSourceMap(record: ResearchRecord | null): SourceMap {
  const map: SourceMap = new Map();
  if (record?.report) {
    for (const s of record.report.sources) map.set(s.id, s);
  }
  return map;
}

function Selector({
  label,
  value,
  options,
  onChange,
  exclude,
}: {
  label: string;
  value: string;
  options: ResearchListItem[];
  onChange: (id: string) => void;
  exclude?: string;
}) {
  return (
    <label className="w-full min-w-0 sm:flex-1">
      <span className="mb-1.5 block text-2xs uppercase tracking-widest text-slateui-500">
        {label}
      </span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-md border border-slateui-600/70 bg-midnight-800 px-3 py-2.5 text-sm text-slateui-100 focus:border-violetui-500/60 focus:outline-none"
      >
        <option value="">Choose a research run…</option>
        {options
          .filter((o) => o.id !== exclude)
          .map((o) => (
            <option key={o.id} value={o.id}>
              {/* Short id disambiguates runs that share query + date */}
              {o.query} — {fmtDate(o.createdAt)} · {o.id.slice(-6)}
            </option>
          ))}
      </select>
    </label>
  );
}

/** Links a finding's cited source ids to the originating report's sources. */
function SourceLinks({ sourceIds, sources }: { sourceIds: string[]; sources: SourceMap }) {
  if (sourceIds.length === 0) {
    return <span className="text-2xs text-slateui-500">No cited source</span>;
  }
  return (
    <span className="flex flex-wrap items-center gap-1.5">
      {sourceIds.map((sid) => {
        const s = sources.get(sid);
        if (!s) {
          return (
            <span key={sid} className="font-mono text-2xs text-slateui-500" title="Source id not found in this report">
              {sid}?
            </span>
          );
        }
        return (
          <a
            key={sid}
            href={s.url}
            target="_blank"
            rel="noopener noreferrer nofollow"
            className="badge badge-neutral transition-colors hover:border-violetui-500/50 hover:text-violetui-300"
            title={`${s.title} — ${s.url}`}
          >
            <Globe size={10} aria-hidden />
            <span className="font-mono">{s.domain}</span>
          </a>
        );
      })}
    </span>
  );
}

function SideBlock({
  label,
  text,
  accentClass,
  sourceIds,
  sources,
}: {
  label: string;
  text: string;
  accentClass: string;
  sourceIds: string[];
  sources: SourceMap;
}) {
  return (
    <div className={`border-l-2 ${accentClass} pl-3`}>
      <p className="mb-0.5 text-2xs uppercase tracking-wider text-slateui-500">{label}</p>
      <p className="text-sm leading-relaxed text-slateui-200">{text}</p>
      <div className="mt-1.5">
        <SourceLinks sourceIds={sourceIds} sources={sources} />
      </div>
    </div>
  );
}

function PairCard({
  pair,
  kind,
  maps,
}: {
  pair: ComparedFindingPair;
  kind: 'exact' | 'similar';
  maps: { a: SourceMap; b: SourceMap };
}) {
  return (
    <li className="panel p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span
          className={
            kind === 'exact'
              ? 'badge-live'
              : 'badge bg-violetui-600/15 text-violetui-300 border border-violetui-500/30'
          }
        >
          {kind === 'exact' ? 'Exact match' : 'Similar claim'}
        </span>
        <span className="text-2xs tabular-nums text-slateui-400">
          {Math.round(pair.similarity * 100)}% token overlap
        </span>
        {pair.sharedSourceIds.length > 0 && (
          <span className="text-2xs text-slateui-500">
            shared source{pair.sharedSourceIds.length === 1 ? '' : 's'}:{' '}
            {pair.sharedSourceIds.join(', ')}
          </span>
        )}
      </div>
      <div className="space-y-2.5">
        <SideBlock
          label={`Run A · finding #${pair.a.index + 1}`}
          text={pair.a.text}
          accentClass="border-l-violetui-500"
          sourceIds={pair.a.sourceIds}
          sources={maps.a}
        />
        <SideBlock
          label={`Run B · finding #${pair.b.index + 1}`}
          text={pair.b.text}
          accentClass="border-l-cyanui-500"
          sourceIds={pair.b.sourceIds}
          sources={maps.b}
        />
      </div>
    </li>
  );
}

function ConflictCard({
  conflict,
  maps,
}: {
  conflict: ReportComparison['conflicts'][number];
  maps: { a: SourceMap; b: SourceMap };
}) {
  const aiJudged = conflict.status === 'ai_reviewed_conflict';
  return (
    <li className="panel border-amber-400/25 p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="badge bg-amber-400/10 text-amber-300 border border-amber-400/30">
          <AlertTriangle size={11} aria-hidden />
          {aiJudged ? 'Model-judged contradiction' : 'Possible conflict'}
        </span>
        {conflict.insufficientEvidence ? (
          <span
            className="badge bg-amber-400/10 text-amber-300 border border-amber-400/30"
            title="Automated matching could not confirm this contradiction — human review of the sources is required."
          >
            Insufficient evidence
          </span>
        ) : (
          <span className="badge-neutral">Reviewed by the model — verify below</span>
        )}
        <span className="text-2xs tabular-nums text-slateui-400">
          {Math.round(conflict.similarity * 100)}% token overlap
        </span>
      </div>
      <div className="space-y-2.5">
        <SideBlock
          label={`Run A · finding #${conflict.a.index + 1}`}
          text={conflict.a.text}
          accentClass="border-l-amber-400/60"
          sourceIds={conflict.a.sourceIds}
          sources={maps.a}
        />
        <SideBlock
          label={`Run B · finding #${conflict.b.index + 1}`}
          text={conflict.b.text}
          accentClass="border-l-amber-400/60"
          sourceIds={conflict.b.sourceIds}
          sources={maps.b}
        />
      </div>
      <p className="mt-3 border-t border-slateui-700/40 pt-2.5 text-xs italic leading-relaxed text-slateui-400">
        {conflict.explanation}
      </p>
    </li>
  );
}

function UniqueList({
  label,
  accentText,
  refs,
  sources,
}: {
  label: string;
  accentText: string;
  refs: ComparedFindingRef[];
  sources: SourceMap;
}) {
  return (
    <div>
      <p className={`mb-2 text-2xs uppercase tracking-widest ${accentText}`}>
        {label} ({refs.length})
      </p>
      {refs.length === 0 ? (
        <p className="text-xs text-slateui-500">None — every finding has a counterpart.</p>
      ) : (
        <ul className="space-y-2">
          {refs.map((ref) => (
            <li key={ref.index} className="panel-subtle p-3">
              <p className="text-xs leading-relaxed text-slateui-300">{ref.text}</p>
              <div className="mt-1.5">
                <SourceLinks sourceIds={ref.sourceIds} sources={sources} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function StatTable({ a, b }: { a: ResearchRecord; b: ResearchRecord }) {
  const ra = a.report;
  const rb = b.report;
  const rows: Array<[string, string, string]> = [
    ['Query', a.query, b.query],
    ['Searched', ra ? fmtDateTime(ra.searchedAt) : fmtDate(a.createdAt), rb ? fmtDateTime(rb.searchedAt) : fmtDate(b.createdAt)],
    ['Results collected', String(a.resultCount), String(b.resultCount)],
    [
      'Full pages retrieved',
      ra ? String(ra.methodology.extractedPageCount) : '—',
      rb ? String(rb.methodology.extractedPageCount) : '—',
    ],
    ['Themes identified', ra ? String(ra.themes.length) : '—', rb ? String(rb.themes.length) : '—'],
    [
      'Key findings',
      ra ? String(ra.keyFindings.length) : '—',
      rb ? String(rb.keyFindings.length) : '—',
    ],
    [
      'Sources',
      ra ? String(ra.sources.length) : '—',
      rb ? String(rb.sources.length) : '—',
    ],
    [
      'Supported / Conflicting / Insufficient',
      ra
        ? `${ra.coverage.supported} / ${ra.coverage.conflicting} / ${ra.coverage.insufficient}`
        : '—',
      rb
        ? `${rb.coverage.supported} / ${rb.coverage.conflicting} / ${rb.coverage.insufficient}`
        : '—',
    ],
  ];
  return (
    <div className="panel overflow-x-auto p-0">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slateui-700/60 text-left">
            <th scope="col" className="px-4 py-3 text-2xs uppercase tracking-widest text-slateui-500">
              Metric
            </th>
            <th scope="col" className="px-4 py-3 text-2xs uppercase tracking-widest text-violetui-400">
              Run A
            </th>
            <th scope="col" className="px-4 py-3 text-2xs uppercase tracking-widest text-cyanui-400">
              Run B
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([metric, va, vb]) => (
            <tr key={metric} className="border-b border-slateui-700/40 last:border-0">
              <th scope="row" className="px-4 py-2.5 font-normal text-slateui-400">{metric}</th>
              <td className="max-w-[28ch] truncate px-4 py-2.5 text-slateui-100" title={va}>{va}</td>
              <td className="max-w-[28ch] truncate px-4 py-2.5 text-slateui-100" title={vb}>{vb}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Run identity card: title, query, and research date for one side. */
function RunIdentity({ label, run, record, accent }: { label: string; run: ComparedRun; record: ResearchRecord | null; accent: string }) {
  return (
    <div className={`panel p-4 ${accent}`}>
      <p className="mb-1 text-2xs uppercase tracking-widest text-slateui-500">{label}</p>
      <Link
        to={`/report/${run.id}`}
        className="font-display text-base font-semibold text-slateui-100 transition-colors hover:text-violetui-300"
        title={run.researchQuestion}
      >
        {run.researchQuestion}
      </Link>
      <p className="mt-1 truncate text-xs text-slateui-400" title={run.query}>
        Query: “{run.query}”
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-2 text-2xs text-slateui-400">
        <span title={fmtDateTime(run.searchedAt)}>Searched {fmtDate(run.searchedAt)}</span>
        <ModeBadge searchMode={run.mode} aiMode={run.aiMode} />
        <span>
          {run.findingCount} findings · {run.sourceCount} sources
        </span>
      </div>
      {record && record.status === 'failed' && record.errorMessage && (
        <p className="mt-2 truncate text-2xs text-red-300/90" title={record.errorMessage}>
          {record.errorMessage}
        </p>
      )}
    </div>
  );
}

export default function Compare() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { status } = useConfigStatus();
  const [list, setList] = useState<ResearchListItem[]>([]);
  const [listError, setListError] = useState<string | null>(null);
  const [idA, setIdA] = useState(searchParams.get('a') ?? '');
  const [idB, setIdB] = useState(searchParams.get('b') ?? '');
  const [sideA, setSideA] = useState<SideState>({ record: null, loading: false, error: null });
  const [sideB, setSideB] = useState<SideState>({ record: null, loading: false, error: null });
  const [useAi, setUseAi] = useState(false);
  const [comparison, setComparison] = useState<ReportComparison | null>(null);
  const [cmpLoading, setCmpLoading] = useState(false);
  const [cmpError, setCmpError] = useState<string | null>(null);
  const [reloadNonce, setReloadNonce] = useState(0);
  const [recordReload, setRecordReload] = useState(0);

  useEffect(() => {
    api
      .listResearch(50, 0)
      .then((res) => setList(res.items))
      .catch((err: unknown) =>
        setListError(err instanceof ApiError ? err.message : 'Could not load research runs.'),
      );
  }, []);

  // Record loading is driven by the selected ids (also covers ?a=&b= links).
  useEffect(() => {
    if (!idA) {
      setSideA({ record: null, loading: false, error: null });
      return;
    }
    let stale = false;
    setSideA({ record: null, loading: true, error: null });
    void loadRecord(idA).then((s) => {
      if (!stale) setSideA(s);
    });
    return () => {
      stale = true;
    };
  }, [idA, recordReload]);

  useEffect(() => {
    if (!idB) {
      setSideB({ record: null, loading: false, error: null });
      return;
    }
    let stale = false;
    setSideB({ record: null, loading: true, error: null });
    void loadRecord(idB).then((s) => {
      if (!stale) setSideB(s);
    });
    return () => {
      stale = true;
    };
  }, [idB, recordReload]);

  // Keep the URL shareable (?a=id&b=id).
  useEffect(() => {
    const next = new URLSearchParams();
    if (idA) next.set('a', idA);
    if (idB) next.set('b', idB);
    setSearchParams(next, { replace: true });
  }, [idA, idB, setSearchParams]);

  // The comparison itself is computed by the backend.
  useEffect(() => {
    if (!idA || !idB || idA === idB) {
      setComparison(null);
      setCmpError(null);
      setCmpLoading(false);
      return;
    }
    let stale = false;
    setCmpLoading(true);
    setCmpError(null);
    api
      .compareReports(idA, idB, useAi ? 'auto' : 'basic')
      .then((result) => {
        if (!stale) setComparison(result);
      })
      .catch((err: unknown) => {
        if (!stale) {
          setCmpError(
            err instanceof ApiError ? err.message : 'Could not compute the comparison.',
          );
        }
      })
      .finally(() => {
        if (!stale) setCmpLoading(false);
      });
    return () => {
      stale = true;
    };
  }, [idA, idB, useAi, reloadNonce]);

  const retryComparison = useCallback(() => setReloadNonce((n) => n + 1), []);

  const sameRun = Boolean(idA && idA === idB);
  const bothSelected = Boolean(idA && idB && !sameRun);
  const maps = useMemo(
    () => ({ a: toSourceMap(sideA.record), b: toSourceMap(sideB.record) }),
    [sideA.record, sideB.record],
  );

  return (
    <div className="space-y-6 animate-fadeUp">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="section-kicker mb-2">Analysis</p>
          <h2 className="font-display text-2xl font-semibold tracking-tight text-slateui-100">
            Compare reports
          </h2>
          <p className="mt-2 max-w-2xl text-sm text-slateui-300">
            Put two stored research runs side by side — shared and unique findings, potential
            conflicts, and source overlap, computed from the records themselves.
          </p>
        </div>
        <Link to="/history" className="btn-ghost text-sm">
          <ArrowLeft size={15} aria-hidden />
          Back to history
        </Link>
      </div>

      <div className="panel flex flex-wrap items-end gap-4 p-5">
        <Selector label="Run A" value={idA} options={list} onChange={setIdA} exclude={idB} />
        <button
          type="button"
          onClick={() => {
            setIdA(idB);
            setIdB(idA);
          }}
          disabled={!idA || !idB}
          className="btn-ghost shrink-0 self-end text-sm disabled:cursor-not-allowed disabled:opacity-40"
          title="Swap Run A and Run B"
          aria-label="Swap Run A and Run B"
        >
          <ArrowLeftRight size={15} aria-hidden />
          Swap
        </button>
        <Selector label="Run B" value={idB} options={list} onChange={setIdB} exclude={idA} />
        <div className="w-full border-t border-slateui-700/40 pt-3">
          {status && status.aiConfigured ? (
            <label className="flex cursor-pointer items-center gap-2 text-xs text-slateui-300">
              <input
                type="checkbox"
                checked={useAi}
                onChange={(e) => setUseAi(e.target.checked)}
                className="h-4 w-4 accent-violetui-600"
              />
              AI-assisted comparison — ask the configured model to judge finding pairs
              {useAi && <span className="text-2xs text-slateui-500">(falls back to basic matching if the model fails)</span>}
            </label>
          ) : (
            status && (
              <p className="text-2xs text-slateui-500">
                AI provider not configured — comparisons use transparent basic text matching.
              </p>
            )
          )}
        </div>
      </div>

      {listError && <ErrorState message={listError} onRetry={() => window.location.reload()} />}

      {sameRun && (
        <p className="rounded-md border border-amber-400/30 bg-amber-400/10 px-4 py-3 text-sm text-amber-300">
          Pick two different research runs to compare.
        </p>
      )}

      {!bothSelected ? (
        <EmptyState
          icon={<GitCompareArrows size={22} aria-hidden />}
          title="Choose two research runs"
          description="Select Run A and Run B above. Any completed run with a stored report can be compared."
        />
      ) : sideA.loading || sideB.loading || cmpLoading ? (
        <SkeletonList count={2} />
      ) : sideA.error || sideB.error || cmpError ? (
        <ErrorState
          title="Comparison unavailable"
          message={sideA.error ?? sideB.error ?? cmpError ?? 'Could not load one of the records.'}
          onRetry={() => {
            setRecordReload((n) => n + 1);
            retryComparison();
          }}
        />
      ) : comparison ? (
        <>
          {/* Run identity — titles, queries, research dates */}
          <div className="grid gap-4 sm:grid-cols-2">
            <RunIdentity label="Run A" run={comparison.runA} record={sideA.record} accent="border-l-2 border-l-violetui-500" />
            <RunIdentity label="Run B" run={comparison.runB} record={sideB.record} accent="border-l-2 border-l-cyanui-500" />
          </div>

          {/* Transparency banner — which mode ran and how */}
          <section
            aria-label="How this comparison was computed"
            className={`panel border-l-2 p-5 ${
              comparison.methodology.mode === 'ai' ? 'border-l-violetui-500' : 'border-l-cyanui-500'
            }`}
          >
            <div className="flex flex-wrap items-center gap-2">
              <span
                className={
                  comparison.methodology.mode === 'ai'
                    ? 'badge bg-violetui-600/15 text-violetui-300 border border-violetui-500/30'
                    : 'badge-live'
                }
              >
                {comparison.methodology.mode === 'ai'
                  ? 'AI-assisted comparison'
                  : 'Basic comparison'}
              </span>
              {comparison.temporalNote && (
                <span className="text-2xs text-slateui-400">{comparison.temporalNote}</span>
              )}
            </div>
            {comparison.methodology.aiNote && (
              <p className="mt-3 flex items-start gap-2 rounded-md border border-amber-400/30 bg-amber-400/10 px-3 py-2 text-xs leading-relaxed text-amber-300">
                <Info size={14} aria-hidden className="mt-0.5 shrink-0" />
                {comparison.methodology.aiNote}
              </p>
            )}
            <ul className="mt-3 space-y-1.5">
              {comparison.methodology.explanation.map((line, i) => (
                <li key={i} className="flex items-start gap-2 text-xs leading-relaxed text-slateui-400">
                  <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-slateui-500" aria-hidden />
                  {line}
                </li>
              ))}
            </ul>
          </section>

          {sideA.record && sideB.record && (
            <StatTable a={sideA.record} b={sideB.record} />
          )}

          {/* Exports */}
          <div className="flex flex-wrap items-center gap-3">
            <a
              href={api.compareMarkdownUrl(idA, idB)}
              download
              className="btn-secondary text-sm"
              title="Download this comparison as Markdown"
            >
              <Download size={15} aria-hidden />
              Export Markdown
            </a>
            <a
              href={api.compareJsonUrl(idA, idB)}
              download
              className="btn-secondary text-sm"
              title="Download this comparison as JSON"
            >
              <FileJson size={15} aria-hidden />
              Export JSON
            </a>
            <a
              href={api.comparePdfUrl(idA, idB)}
              download
              className="btn-secondary text-sm"
              title="Download this comparison as PDF"
            >
              <FileDown size={15} aria-hidden />
              Export PDF
            </a>
          </div>

          {comparison.runA.findingCount === 0 && comparison.runB.findingCount === 0 ? (
            <EmptyState
              title="No findings to compare"
              description="Neither run produced stored findings, so there is nothing to overlap yet."
            />
          ) : (
            <>
              {/* Shared findings (exact matches) */}
              <section aria-labelledby="cmp-shared">
                <h3 id="cmp-shared" className="section-title mb-3">
                  Shared findings ({comparison.sharedFindings.length})
                </h3>
                {comparison.sharedFindings.length === 0 ? (
                  <p className="panel p-4 text-sm text-slateui-400">
                    No identical findings appear in both runs.
                  </p>
                ) : (
                  <ul className="grid gap-4 xl:grid-cols-2">
                    {comparison.sharedFindings.map((pair) => (
                      <PairCard key={`exact-${pair.a.index}-${pair.b.index}`} pair={pair} kind="exact" maps={maps} />
                    ))}
                  </ul>
                )}
              </section>

              {/* Similar findings */}
              <section aria-labelledby="cmp-similar">
                <h3 id="cmp-similar" className="section-title mb-3">
                  Similar findings ({comparison.similarFindings.length})
                </h3>
                {comparison.similarFindings.length === 0 ? (
                  <p className="panel p-4 text-sm text-slateui-400">
                    No sufficiently similar finding pairs were found between the runs.
                  </p>
                ) : (
                  <ul className="grid gap-4 xl:grid-cols-2">
                    {comparison.similarFindings.map((pair) => (
                      <PairCard key={`similar-${pair.a.index}-${pair.b.index}`} pair={pair} kind="similar" maps={maps} />
                    ))}
                  </ul>
                )}
              </section>

              {/* Potential conflicts */}
              <section aria-labelledby="cmp-conflicts">
                <h3 id="cmp-conflicts" className="section-title mb-3">
                  Potential conflicts ({comparison.conflicts.length})
                </h3>
                {comparison.conflicts.length === 0 ? (
                  <p className="panel p-4 text-sm text-slateui-400">
                    No potential conflicts were detected. Absence of detected conflict does not
                    mean the two runs agree.
                  </p>
                ) : (
                  <ul className="space-y-4">
                    {comparison.conflicts.map((conflict) => (
                      <ConflictCard
                        key={`conflict-${conflict.a.index}-${conflict.b.index}`}
                        conflict={conflict}
                        maps={maps}
                      />
                    ))}
                  </ul>
                )}
              </section>

              {/* Unique findings */}
              <section aria-labelledby="cmp-unique">
                <h3 id="cmp-unique" className="section-title mb-3">
                  Findings unique to each run
                </h3>
                <div className="grid gap-5 lg:grid-cols-2">
                  <UniqueList
                    label="Only in Run A"
                    accentText="text-violetui-400"
                    refs={comparison.uniqueToA}
                    sources={maps.a}
                  />
                  <UniqueList
                    label="Only in Run B"
                    accentText="text-cyanui-400"
                    refs={comparison.uniqueToB}
                    sources={maps.b}
                  />
                </div>
                <p className="mt-3 flex items-start gap-2 rounded-md border border-blueui-500/30 bg-blueui-500/10 px-3 py-2 text-xs leading-relaxed text-blueui-400">
                  <Info size={14} aria-hidden className="mt-0.5 shrink-0" />
                  {comparison.noveltyCaveat}
                </p>
              </section>
            </>
          )}

          {/* Source differences */}
          <section aria-labelledby="cmp-sources">
            <h3 id="cmp-sources" className="section-title mb-3">Source differences</h3>
            <div className="panel p-5">
              <p className="text-sm text-slateui-300">
                <span className="font-semibold text-slateui-100">{comparison.sources.sharedCount}</span>{' '}
                of {comparison.runA.sourceCount} / {comparison.runB.sourceCount} sources appear in
                both runs (matched by exact URL).
              </p>
              <div className="mt-3 grid grid-cols-3 gap-px overflow-hidden rounded-md border border-slateui-700/40 bg-slateui-700/40">
                {[
                  { label: 'Shared URLs', value: comparison.sources.sharedCount },
                  { label: 'Only in A', value: comparison.sources.onlyACount },
                  { label: 'Only in B', value: comparison.sources.onlyBCount },
                ].map((cell) => (
                  <div key={cell.label} className="bg-midnight-800 px-4 py-3">
                    <p className="text-2xs uppercase tracking-wider text-slateui-500">{cell.label}</p>
                    <p className="mt-0.5 font-display text-xl font-semibold tabular-nums text-slateui-100">
                      {cell.value}
                    </p>
                  </div>
                ))}
              </div>
              {comparison.sources.sharedUrls.length > 0 && (
                <ul className="mt-3 space-y-1">
                  {comparison.sources.sharedUrls.map((url) => (
                    <li key={url} className="truncate" title={url}>
                      <a
                        href={url}
                        target="_blank"
                        rel="noopener noreferrer nofollow"
                        className="font-mono text-2xs text-slateui-500 transition-colors hover:text-violetui-300"
                      >
                        {url}
                      </a>
                    </li>
                  ))}
                  {comparison.sources.sharedCount > comparison.sources.sharedUrls.length && (
                    <li className="text-2xs text-slateui-500">
                      +{comparison.sources.sharedCount - comparison.sources.sharedUrls.length} more
                      shared URLs
                    </li>
                  )}
                </ul>
              )}
              {comparison.sources.sharedDomains.length > 0 && (
                <div className="mt-3 flex flex-wrap items-center gap-1.5">
                  <span className="text-2xs text-slateui-500">Shared domains:</span>
                  {comparison.sources.sharedDomains.map((domain) => (
                    <span key={domain} className="badge badge-neutral font-mono">
                      {domain}
                    </span>
                  ))}
                </div>
              )}
              <p className="mt-3 text-2xs leading-relaxed text-slateui-500">
                Domain overlap is informational — the same domain does not imply the same source.
              </p>
            </div>
          </section>
        </>
      ) : null}
    </div>
  );
}
