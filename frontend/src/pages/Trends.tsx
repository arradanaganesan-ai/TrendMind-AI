import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ArrowLeft, Info, Plus, Trash2, TrendingUp } from 'lucide-react';
import ConfirmDialog from '../components/ui/ConfirmDialog';
import EmptyState from '../components/ui/EmptyState';
import ErrorState from '../components/ui/ErrorState';
import ModeBadge from '../components/ui/ModeBadge';
import { SkeletonList } from '../components/ui/Skeletons';
import { TrendHistoryChart } from '../components/charts/AnalyticsCharts';
import { useConfigStatus } from '../hooks/useConfigStatus';
import { api, ApiError } from '../services/api';
import type {
  ComparedFindingRef,
  SnapshotChange,
  SnapshotTheme,
  SourceRef,
  TimelineSnapshot,
  TrendCandidate,
  TrendTimeline,
  TrackedTopic,
} from '../types/api';

/**
 * Historical trend tracking. A tracked topic is one research query; each
 * snapshot is a REAL dated research run stored for that query — this page
 * never fabricates history. The timeline shows snapshots oldest-first with
 * deterministic changes between consecutive ones; the chart only renders
 * when at least two dated snapshots exist (a single point is not a trend).
 * "No longer observed" always means absent from the newer search, never
 * proven false.
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

function confidenceAccent(confidence: SnapshotTheme['confidence']): string {
  switch (confidence) {
    case 'strong':
      return 'bg-cyanui-500';
    case 'moderate':
      return 'bg-violetui-500';
    case 'emerging':
      return 'bg-amber-400';
    default:
      return 'bg-slateui-500';
  }
}

type SourceMap = Map<string, SourceRef>;

function toSourceMap(sources: SourceRef[]): SourceMap {
  const map: SourceMap = new Map();
  for (const s of sources) map.set(s.id, s);
  return map;
}

/** Cited source ids of a finding, resolved to clickable domain badges. */
function FindingSourceLinks({ sourceIds, sources }: { sourceIds: string[]; sources: SourceMap }) {
  if (sourceIds.length === 0) {
    return <span className="text-2xs text-slateui-500">No cited source</span>;
  }
  return (
    <span className="flex flex-wrap items-center gap-1.5">
      {sourceIds.map((sid) => {
        const s = sources.get(sid);
        if (!s) return null;
        return (
          <a
            key={sid}
            href={s.url}
            target="_blank"
            rel="noopener noreferrer nofollow"
            className="badge badge-neutral transition-colors hover:border-violetui-500/50 hover:text-violetui-300"
            title={`${s.title} — ${s.url}`}
          >
            <span className="font-mono">{s.domain}</span>
          </a>
        );
      })}
    </span>
  );
}

function FindingsList({ refs, sources }: { refs: ComparedFindingRef[]; sources: SourceMap }) {
  return (
    <ul className="space-y-2">
      {refs.map((ref) => (
        <li key={ref.index} className="panel-subtle p-3">
          <p className="text-xs leading-relaxed text-slateui-300">{ref.text}</p>
          <div className="mt-1.5">
            <FindingSourceLinks sourceIds={ref.sourceIds} sources={sources} />
          </div>
        </li>
      ))}
    </ul>
  );
}

function ThemeStrengthBars({ themes }: { themes: SnapshotTheme[] }) {
  if (themes.length === 0) {
    return <p className="text-xs text-slateui-500">No themes were identified in this snapshot.</p>;
  }
  return (
    <ul className="space-y-2.5">
      {themes.map((t) => (
        <li key={t.name}>
          <div className="flex items-baseline justify-between gap-2">
            <span className="truncate text-xs text-slateui-200" title={t.name}>
              {t.name}
            </span>
            <span className="shrink-0 text-2xs tabular-nums text-slateui-400">
              {t.evidenceStrength}/100 · {t.mentionCount} source{t.mentionCount === 1 ? '' : 's'} ·{' '}
              {t.confidence}
            </span>
          </div>
          <div
            className="mt-1 h-1.5 overflow-hidden rounded-full bg-midnight-700"
            role="img"
            aria-label={`${t.name}: evidence strength ${t.evidenceStrength} of 100, ${t.confidence}`}
          >
            <div
              className={`h-full rounded-full ${confidenceAccent(t.confidence)}`}
              style={{ width: `${Math.max(2, t.evidenceStrength)}%` }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}

/** One dated snapshot: real timestamp, mode, counts, and expandable details. */
function SnapshotCard({ snapshot }: { snapshot: TimelineSnapshot }) {
  const sources = useMemo(() => toSourceMap(snapshot.sources), [snapshot.sources]);
  return (
    <li className="panel border-l-2 border-l-violetui-500/60 p-4">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
        <span
          className="h-2.5 w-2.5 shrink-0 rounded-full bg-violetui-500"
          aria-hidden
        />
        <p className="text-sm font-medium text-slateui-100" title={snapshot.searchedAt}>
          {fmtDateTime(snapshot.searchedAt)}
        </p>
        <span className="text-2xs tabular-nums text-slateui-500">· {snapshot.researchId.slice(-6)}</span>
        <ModeBadge searchMode={snapshot.mode} aiMode={snapshot.aiMode} />
        <span className="text-2xs text-slateui-400">
          {snapshot.findingCount} findings · {snapshot.sourceCount} sources ·{' '}
          {snapshot.domainCount} domains
        </span>
        <Link
          to={`/report/${snapshot.researchId}`}
          className="ml-auto text-xs text-violetui-300 transition-colors hover:text-violetui-200"
        >
          Open full report
        </Link>
      </div>
      <details className="group mt-3 border-t border-slateui-700/40 pt-3">
        <summary className="cursor-pointer list-none text-xs text-slateui-400 transition-colors hover:text-slateui-200">
          <span className="group-open:hidden">Show snapshot details</span>
          <span className="hidden group-open:inline">Hide snapshot details</span>
        </summary>
        <div className="mt-3 grid gap-5 lg:grid-cols-2">
          <div>
            <p className="mb-2 text-2xs uppercase tracking-widest text-slateui-500">
              Key findings ({snapshot.findingCount})
            </p>
            {snapshot.findings.length === 0 ? (
              <p className="text-xs text-slateui-500">No findings were stored for this run.</p>
            ) : (
              <FindingsList refs={snapshot.findings} sources={sources} />
            )}
          </div>
          <div>
            <p className="mb-2 text-2xs uppercase tracking-widest text-slateui-500">
              Sources ({snapshot.sourceCount})
            </p>
            {snapshot.sources.length === 0 ? (
              <p className="text-xs text-slateui-500">No sources were collected for this run.</p>
            ) : (
              <ul className="space-y-1">
                {snapshot.sources.map((s) => (
                  <li key={s.id} className="truncate text-xs" title={s.url}>
                    <a
                      href={s.url}
                      target="_blank"
                      rel="noopener noreferrer nofollow"
                      className="text-slateui-400 transition-colors hover:text-violetui-300"
                    >
                      <span className="font-mono text-2xs text-slateui-500">{s.id}</span>{' '}
                      {s.title || s.url}
                    </a>
                  </li>
                ))}
              </ul>
            )}
            <div className="mt-4">
              <p className="mb-2 text-2xs uppercase tracking-widest text-slateui-500">
                Themes &amp; evidence strength
              </p>
              <ThemeStrengthBars themes={snapshot.themes} />
            </div>
          </div>
        </div>
      </details>
    </li>
  );
}

function UrlList({ title, urls, accent }: { title: string; urls: string[]; accent: string }) {
  if (urls.length === 0) return null;
  return (
    <div>
      <p className={`mb-1 text-2xs uppercase tracking-wider ${accent}`}>{title}</p>
      <ul className="space-y-0.5">
        {urls.map((url) => (
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
      </ul>
    </div>
  );
}

/** Deterministic deltas between two consecutive dated snapshots. */
function ChangeCard({
  change,
  olderSources,
  newerSources,
}: {
  change: SnapshotChange;
  olderSources: SourceMap;
  newerSources: SourceMap;
}) {
  const coverage = change.sourceCoverage;
  return (
    <li className="panel p-5">
      <div className="flex flex-wrap items-center gap-2">
        <h4 className="text-sm font-semibold text-slateui-100">
          {fmtDate(change.fromSnapshot.searchedAt)} → {fmtDate(change.toSnapshot.searchedAt)}
        </h4>
        <span className="badge badge-neutral tabular-nums">
          {change.daysApart === 0 ? 'same day' : `${change.daysApart} days apart`}
        </span>
        <span className="text-2xs text-slateui-400">
          {change.unchangedCount} finding{change.unchangedCount === 1 ? '' : 's'} observed in both
        </span>
      </div>

      <p className="mt-3 flex items-start gap-2 rounded-md border border-blueui-500/30 bg-blueui-500/10 px-3 py-2 text-xs leading-relaxed text-blueui-400">
        <Info size={14} aria-hidden className="mt-0.5 shrink-0" />
        {change.absenceCaveat}
      </p>

      <div className="mt-4 grid gap-5 lg:grid-cols-2">
        <div>
          <p className="mb-1 text-2xs uppercase tracking-widest text-cyanui-400">
            Newly observed ({change.newlyObserved.length})
          </p>
          <p className="mb-2 text-2xs leading-relaxed text-slateui-500">
            Present in the {fmtDate(change.toSnapshot.searchedAt)} snapshot but not in the previous
            one — not proof the claim is new.
          </p>
          {change.newlyObserved.length === 0 ? (
            <p className="text-xs text-slateui-500">None — no new findings surfaced.</p>
          ) : (
            <FindingsList refs={change.newlyObserved} sources={newerSources} />
          )}
        </div>
        <div>
          <p className="mb-1 text-2xs uppercase tracking-widest text-amber-300">
            No longer observed ({change.noLongerObserved.length})
          </p>
          <p className="mb-2 text-2xs leading-relaxed text-slateui-500">
            Observed on {fmtDate(change.fromSnapshot.searchedAt)} but not returned by the newer
            search. This does NOT mean the claim was disproven.
          </p>
          {change.noLongerObserved.length === 0 ? (
            <p className="text-xs text-slateui-500">
              None — every previous finding was observed again.
            </p>
          ) : (
            <FindingsList refs={change.noLongerObserved} sources={olderSources} />
          )}
        </div>
      </div>

      <div className="mt-5 border-t border-slateui-700/40 pt-4">
        <p className="mb-2 text-2xs uppercase tracking-widest text-slateui-500">
          Source coverage (matched by exact URL)
        </p>
        <div className="grid grid-cols-3 gap-px overflow-hidden rounded-md border border-slateui-700/40 bg-slateui-700/40">
          {[
            { label: 'Shared', value: coverage.sharedCount },
            { label: 'Added in newer', value: coverage.addedCount },
            { label: 'Missing in newer', value: coverage.removedCount },
          ].map((cell) => (
            <div key={cell.label} className="bg-midnight-800 px-3 py-2">
              <p className="text-2xs uppercase tracking-wider text-slateui-500">{cell.label}</p>
              <p className="font-display text-lg font-semibold tabular-nums text-slateui-100">
                {cell.value}
              </p>
            </div>
          ))}
        </div>
        {(coverage.addedDomains.length > 0 || coverage.removedDomains.length > 0) && (
          <div className="mt-3 flex flex-wrap items-center gap-1.5">
            {coverage.addedDomains.map((d) => (
              <span key={`+${d}`} className="badge badge-neutral font-mono">
                +{d}
              </span>
            ))}
            {coverage.removedDomains.map((d) => (
              <span key={`-${d}`} className="badge badge-neutral font-mono">
                −{d}
              </span>
            ))}
          </div>
        )}
        <div className="mt-3 grid gap-4 sm:grid-cols-2">
          <UrlList
            title="URLs only in newer"
            urls={coverage.addedUrls}
            accent="text-cyanui-400"
          />
          <UrlList
            title="URLs no longer present"
            urls={coverage.removedUrls}
            accent="text-amber-300"
          />
        </div>
      </div>

      <div className="mt-5 border-t border-slateui-700/40 pt-4">
        <p className="mb-2 text-2xs uppercase tracking-widest text-slateui-500">
          Theme evidence-strength changes (themes observed in both snapshots)
        </p>
        {change.themeScoreChanges.length === 0 ? (
          <p className="text-xs text-slateui-500">
            No strength changes among themes that appear in both snapshots.
          </p>
        ) : (
          <ul className="space-y-1.5">
            {change.themeScoreChanges.map((t) => (
              <li
                key={t.theme}
                className="flex flex-wrap items-baseline gap-2 rounded-md border border-slateui-700/40 px-3 py-1.5 text-xs"
              >
                <span className="flex-1 text-slateui-200">{t.theme}</span>
                <span className="tabular-nums text-slateui-400">
                  {t.olderStrength} → {t.newerStrength}
                </span>
                <span
                  className={`tabular-nums font-semibold ${
                    t.delta > 0 ? 'text-cyanui-300' : 'text-amber-300'
                  }`}
                >
                  {t.delta > 0 ? `+${t.delta}` : t.delta}
                </span>
              </li>
            ))}
          </ul>
        )}
        {change.incomparableThemes.length > 0 && (
          <div className="mt-3">
            <p className="mb-1.5 text-2xs leading-relaxed text-slateui-500">
              Not comparable (theme appears in only one of the two snapshots — no score change is
              estimated):
            </p>
            <div className="flex flex-wrap gap-1.5">
              {change.incomparableThemes.map((name) => (
                <span key={name} className="badge badge-neutral">
                  {name}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </li>
  );
}

function TopicCard({
  topic,
  onOpen,
  onDelete,
}: {
  topic: TrackedTopic;
  onOpen: () => void;
  onDelete: () => void;
}) {
  return (
    <li className="panel flex flex-col p-5">
      <p className="font-display text-base font-semibold leading-snug text-slateui-100">
        {topic.query}
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-2 text-2xs text-slateui-400">
        <span className="badge badge-neutral tabular-nums">
          {topic.snapshotCount} snapshot{topic.snapshotCount === 1 ? '' : 's'}
        </span>
        {topic.firstSnapshotAt && topic.lastSnapshotAt && (
          <span title={fmtDateTime(topic.firstSnapshotAt)}>
            {fmtDate(topic.firstSnapshotAt)} → {fmtDate(topic.lastSnapshotAt)}
          </span>
        )}
      </div>
      <div className="mt-4 flex items-center gap-2 pt-1">
        <button type="button" onClick={onOpen} className="btn-secondary text-sm">
          View timeline
        </button>
        <button
          type="button"
          onClick={onDelete}
          className="btn-ghost ml-auto text-sm text-slateui-400 hover:text-red-300"
          aria-label={`Stop tracking “${topic.query}”`}
          title="Stop tracking this topic (stored research runs are kept)"
        >
          <Trash2 size={15} aria-hidden />
          Untrack
        </button>
      </div>
    </li>
  );
}

export default function Trends() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { status } = useConfigStatus();

  // Topic list + tracker picker
  const [topics, setTopics] = useState<TrackedTopic[] | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<TrendCandidate[]>([]);
  const [createQuery, setCreateQuery] = useState('');
  const [createError, setCreateError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<TrackedTopic | null>(null);

  // Selected timeline (?topic=&from=&to=)
  const [selectedId, setSelectedId] = useState(searchParams.get('topic') ?? '');
  const [dateFrom, setDateFrom] = useState(searchParams.get('from') ?? '');
  const [dateTo, setDateTo] = useState(searchParams.get('to') ?? '');
  const [useAi, setUseAi] = useState(false);
  const [timeline, setTimeline] = useState<TrendTimeline | null>(null);
  const [tlLoading, setTlLoading] = useState(false);
  const [tlError, setTlError] = useState<string | null>(null);
  const [reloadNonce, setReloadNonce] = useState(0);

  const refreshTopics = useCallback(() => {
    api
      .listTrackedTopics()
      .then((res) => {
        setTopics(res.items);
        setListError(null);
      })
      .catch((err: unknown) => {
        setTopics((prev) => prev ?? []);
        setListError(err instanceof ApiError ? err.message : 'Could not load tracked topics.');
      });
  }, []);

  useEffect(() => {
    refreshTopics();
    api
      .trendCandidates()
      .then((res) => setCandidates(res.items))
      .catch(() => setCandidates([]));
  }, [refreshTopics]);

  // Keep the URL shareable (?topic=id&from=YYYY-MM-DD&to=YYYY-MM-DD).
  useEffect(() => {
    const next = new URLSearchParams();
    if (selectedId) next.set('topic', selectedId);
    if (dateFrom) next.set('from', dateFrom);
    if (dateTo) next.set('to', dateTo);
    setSearchParams(next, { replace: true });
  }, [selectedId, dateFrom, dateTo, setSearchParams]);

  // The timeline itself (snapshots + deterministic changes) comes from the backend.
  useEffect(() => {
    if (!selectedId) {
      setTimeline(null);
      setTlError(null);
      setTlLoading(false);
      return;
    }
    let stale = false;
    setTlLoading(true);
    setTlError(null);
    api
      .getTrendTimeline(selectedId, {
        dateFrom: dateFrom || undefined,
        dateTo: dateTo || undefined,
        mode: useAi ? 'auto' : 'basic',
      })
      .then((result) => {
        if (!stale) setTimeline(result);
      })
      .catch((err: unknown) => {
        if (!stale) {
          setTimeline(null);
          setTlError(err instanceof ApiError ? err.message : 'Could not load the timeline.');
        }
      })
      .finally(() => {
        if (!stale) setTlLoading(false);
      });
    return () => {
      stale = true;
    };
  }, [selectedId, dateFrom, dateTo, useAi, reloadNonce]);

  const trackTopic = useCallback(async () => {
    if (!createQuery) return;
    setCreating(true);
    setCreateError(null);
    try {
      const topic = await api.trackTopic(createQuery);
      setTopics((prev) => {
        const list = prev ?? [];
        return list.some((t) => t.id === topic.id) ? list : [topic, ...list];
      });
      setCreateQuery('');
      setSelectedId(topic.id);
    } catch (err: unknown) {
      setCreateError(err instanceof ApiError ? err.message : 'Could not track this topic.');
    } finally {
      setCreating(false);
    }
  }, [createQuery]);

  const confirmDelete = useCallback(async () => {
    if (!deleteTarget) return;
    try {
      await api.deleteTrackedTopic(deleteTarget.id);
      setTopics((prev) => (prev ?? []).filter((t) => t.id !== deleteTarget.id));
      if (selectedId === deleteTarget.id) {
        setSelectedId('');
        setTimeline(null);
      }
    } catch (err: unknown) {
      setListError(err instanceof ApiError ? err.message : 'Could not delete this topic.');
    } finally {
      setDeleteTarget(null);
    }
  }, [deleteTarget, selectedId]);

  // Source maps per snapshot, for resolving cited ids in change findings.
  const sourceMaps = useMemo(() => {
    const maps = new Map<string, SourceMap>();
    for (const s of timeline?.snapshots ?? []) maps.set(s.researchId, toSourceMap(s.sources));
    return maps;
  }, [timeline]);

  const trackedQueries = useMemo(
    () => new Set((topics ?? []).map((t) => t.query)),
    [topics],
  );
  const openCandidates = candidates.filter((c) => !trackedQueries.has(c.query));

  const selectedTopic = (topics ?? []).find((t) => t.id === selectedId) ?? null;
  const hasDateFilter = Boolean(dateFrom || dateTo);

  // -------------------------------------------------------------------------
  // Timeline view
  // -------------------------------------------------------------------------
  if (selectedId) {
    return (
      <div className="space-y-6 animate-fadeUp">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="section-kicker mb-2">History</p>
            <h2 className="font-display text-2xl font-semibold tracking-tight text-slateui-100">
              {selectedTopic?.query ?? 'Tracked topic'}
            </h2>
            <p className="mt-2 max-w-2xl text-sm text-slateui-300">
              Dated snapshots of this query from real stored research runs, with deterministic
              change detection between consecutive snapshots.
            </p>
          </div>
          <Link to="/trends" className="btn-ghost text-sm">
            <ArrowLeft size={15} aria-hidden />
            Back to topics
          </Link>
        </div>

        {/* Controls: date filters + optional AI summary */}
        <div className="panel flex flex-wrap items-end gap-4 p-5">
          <label className="flex items-center gap-1.5 text-xs text-slateui-400">
            From
            <input
              type="date"
              value={dateFrom}
              max={dateTo || undefined}
              onChange={(e) => setDateFrom(e.target.value)}
              className="rounded-md border border-slateui-600/70 bg-midnight-800 px-2 py-1 text-xs text-slateui-200 focus:border-violetui-500/60 focus:outline-none"
            />
          </label>
          <label className="flex items-center gap-1.5 text-xs text-slateui-400">
            To
            <input
              type="date"
              value={dateTo}
              min={dateFrom || undefined}
              onChange={(e) => setDateTo(e.target.value)}
              className="rounded-md border border-slateui-600/70 bg-midnight-800 px-2 py-1 text-xs text-slateui-200 focus:border-violetui-500/60 focus:outline-none"
            />
          </label>
          {hasDateFilter && (
            <button
              type="button"
              className="btn-ghost text-xs"
              onClick={() => {
                setDateFrom('');
                setDateTo('');
              }}
            >
              Clear dates
            </button>
          )}
          <div className="w-full border-t border-slateui-700/40 pt-3">
            {status && status.aiConfigured ? (
              <label className="flex cursor-pointer items-center gap-2 text-xs text-slateui-300">
                <input
                  type="checkbox"
                  checked={useAi}
                  onChange={(e) => setUseAi(e.target.checked)}
                  className="h-4 w-4 accent-violetui-600"
                />
                AI summary of changes — ask the configured model to summarize the deterministic
                deltas
                {useAi && (
                  <span className="text-2xs text-slateui-500">
                    (falls back to basic analysis if the model fails)
                  </span>
                )}
              </label>
            ) : (
              status && (
                <p className="text-2xs text-slateui-500">
                  AI provider not configured — changes use transparent deterministic analysis.
                </p>
              )
            )}
          </div>
        </div>

        {tlLoading ? (
          <SkeletonList count={2} />
        ) : tlError ? (
          <ErrorState title="Timeline unavailable" message={tlError} onRetry={() => setReloadNonce((n) => n + 1)} />
        ) : timeline ? (
          <>
            {/* Transparency banner — which mode ran and how */}
            <section
              aria-label="How this timeline was computed"
              className={`panel border-l-2 p-5 ${
                timeline.methodology.mode === 'ai' ? 'border-l-violetui-500' : 'border-l-cyanui-500'
              }`}
            >
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={
                    timeline.methodology.mode === 'ai'
                      ? 'badge bg-violetui-600/15 text-violetui-300 border border-violetui-500/30'
                      : 'badge-live'
                  }
                >
                  {timeline.methodology.mode === 'ai'
                    ? 'AI-assisted change summary'
                    : 'Basic trend analysis'}
                </span>
                <span className="text-2xs tabular-nums text-slateui-400">
                  {timeline.snapshots.length} dated snapshot
                  {timeline.snapshots.length === 1 ? '' : 's'}
                  {hasDateFilter ? ' in range' : ''}
                </span>
              </div>
              {timeline.methodology.aiNote && (
                <p className="mt-3 flex items-start gap-2 rounded-md border border-amber-400/30 bg-amber-400/10 px-3 py-2 text-xs leading-relaxed text-amber-300">
                  <Info size={14} aria-hidden className="mt-0.5 shrink-0" />
                  {timeline.methodology.aiNote}
                </p>
              )}
              {timeline.methodology.aiSummary && (
                <div className="mt-3 rounded-md border border-violetui-500/30 bg-violetui-600/10 px-3 py-2">
                  <p className="mb-1 text-2xs uppercase tracking-widest text-violetui-300">
                    Model summary — verify against the sources below
                  </p>
                  <p className="text-xs leading-relaxed text-slateui-200">
                    {timeline.methodology.aiSummary}
                  </p>
                </div>
              )}
              <ul className="mt-3 space-y-1.5">
                {timeline.methodology.explanation.map((line, i) => (
                  <li key={i} className="flex items-start gap-2 text-xs leading-relaxed text-slateui-400">
                    <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-slateui-500" aria-hidden />
                    {line}
                  </li>
                ))}
              </ul>
            </section>

            {timeline.snapshots.length === 0 ? (
              <EmptyState
                icon={<TrendingUp size={22} aria-hidden />}
                title="No dated snapshots in this range"
                description={
                  hasDateFilter
                    ? 'No stored research runs for this query fall within the selected dates. Clear the date filters to see every available snapshot.'
                    : 'All stored research runs for this query were removed, so there is no snapshot history to show yet.'
                }
                action={
                  hasDateFilter ? (
                    <button
                      type="button"
                      className="btn-secondary text-sm"
                      onClick={() => {
                        setDateFrom('');
                        setDateTo('');
                      }}
                    >
                      Clear date filters
                    </button>
                  ) : (
                    <Link to="/research" className="btn-secondary text-sm">
                      Run new research
                    </Link>
                  )
                }
              />
            ) : (
              <>
                {timeline.singleSnapshotNote ? (
                  <p className="flex items-start gap-2 rounded-md border border-blueui-500/30 bg-blueui-500/10 px-4 py-3 text-sm leading-relaxed text-blueui-400">
                    <Info size={16} aria-hidden className="mt-0.5 shrink-0" />
                    {timeline.singleSnapshotNote}
                  </p>
                ) : (
                  <TrendHistoryChart snapshots={timeline.snapshots} />
                )}

                <section aria-labelledby="tl-snapshots">
                  <h3 id="tl-snapshots" className="section-title mb-3">
                    Snapshots (oldest first)
                  </h3>
                  <ul className="space-y-4">
                    {timeline.snapshots.map((snap) => (
                      <SnapshotCard key={snap.researchId} snapshot={snap} />
                    ))}
                  </ul>
                </section>

                {timeline.changes.length > 0 && (
                  <section aria-labelledby="tl-changes">
                    <h3 id="tl-changes" className="section-title mb-3">
                      Changes between consecutive snapshots ({timeline.changes.length})
                    </h3>
                    <ul className="space-y-4">
                      {timeline.changes.map((change) => (
                        <ChangeCard
                          key={`${change.fromSnapshot.researchId}-${change.toSnapshot.researchId}`}
                          change={change}
                          olderSources={
                            sourceMaps.get(change.fromSnapshot.researchId) ?? new Map()
                          }
                          newerSources={
                            sourceMaps.get(change.toSnapshot.researchId) ?? new Map()
                          }
                        />
                      ))}
                    </ul>
                  </section>
                )}
              </>
            )}
          </>
        ) : null}
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // Topic list view
  // -------------------------------------------------------------------------
  return (
    <div className="space-y-6 animate-fadeUp">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="section-kicker mb-2">History</p>
          <h2 className="font-display text-2xl font-semibold tracking-tight text-slateui-100">
            Trend tracking
          </h2>
          <p className="mt-2 max-w-2xl text-sm text-slateui-300">
            Follow an existing research query over time. Each snapshot is a real dated research
            run — the timeline shows what was actually observed on each date, and a finding missing
            from a newer search is never treated as disproven.
          </p>
        </div>
        <Link to="/history" className="btn-ghost text-sm">
          <ArrowLeft size={15} aria-hidden />
          Research history
        </Link>
      </div>

      {/* Track a new topic — options come from real completed runs */}
      <div className="panel flex flex-wrap items-end gap-4 p-5">
        <label className="w-full min-w-0 sm:flex-1">
          <span className="mb-1.5 block text-2xs uppercase tracking-widest text-slateui-500">
            Track an existing research query
          </span>
          <select
            value={createQuery}
            onChange={(e) => {
              setCreateQuery(e.target.value);
              setCreateError(null);
            }}
            className="w-full rounded-md border border-slateui-600/70 bg-midnight-800 px-3 py-2.5 text-sm text-slateui-100 focus:border-violetui-500/60 focus:outline-none"
          >
            <option value="">
              {candidates.length === 0
                ? 'No completed research runs yet…'
                : 'Choose a query to follow…'}
            </option>
            {openCandidates.map((c) => (
              <option key={c.query} value={c.query}>
                {c.query} — {c.runCount} run{c.runCount === 1 ? '' : 's'}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={() => void trackTopic()}
          disabled={!createQuery || creating}
          className="btn-primary shrink-0 text-sm disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Plus size={15} aria-hidden />
          Track topic
        </button>
        {candidates.length === 0 && (
          <p className="w-full text-2xs text-slateui-500">
            Run some research first — only queries with completed runs can be tracked, so every
            topic starts with at least one real snapshot.
          </p>
        )}
        {createError && (
          <p className="w-full rounded-md border border-amber-400/30 bg-amber-400/10 px-3 py-2 text-xs leading-relaxed text-amber-300">
            {createError}
          </p>
        )}
      </div>

      {listError && <ErrorState message={listError} onRetry={refreshTopics} />}

      {topics === null ? (
        <SkeletonList count={2} />
      ) : topics.length === 0 ? (
        <EmptyState
          icon={<TrendingUp size={22} aria-hidden />}
          title="No tracked topics yet"
          description="Pick a research query above to start following it. Snapshots appear automatically as new research runs with the same query are stored."
        />
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {topics.map((topic) => (
            <TopicCard
              key={topic.id}
              topic={topic}
              onOpen={() => setSelectedId(topic.id)}
              onDelete={() => setDeleteTarget(topic)}
            />
          ))}
        </ul>
      )}

      <ConfirmDialog
        open={deleteTarget !== null}
        title="Stop tracking this topic?"
        description={`“${deleteTarget?.query ?? ''}” will be removed from trend tracking. The stored research runs themselves are kept and remain available in Research History.`}
        confirmLabel="Untrack"
        danger
        onConfirm={() => void confirmDelete()}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
