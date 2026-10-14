import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  ArrowRight,
  Bookmark,
  CalendarDays,
  Clock,
  FileCheck,
  FileText,
  Info,
  Lightbulb,
  Plus,
  RotateCcw,
  Search,
  Settings2,
  Trash2,
  TrendingUp,
} from 'lucide-react';
import ResearchForm from '../components/search/ResearchForm';
import EmptyState from '../components/ui/EmptyState';
import ErrorState from '../components/ui/ErrorState';
import { SkeletonList } from '../components/ui/Skeletons';
import ModeBadge from '../components/ui/ModeBadge';
import ConfirmDialog from '../components/ui/ConfirmDialog';
import { ActivityChart } from '../components/charts/AnalyticsCharts';
import { useToast } from '../hooks/useToast';
import { useConfigStatus } from '../hooks/useConfigStatus';
import { api, ApiError } from '../services/api';
import type {
  ActivityPoint,
  ResearchListItem,
  ResearchRequest,
  ResearchStatus,
  SavedTopic,
  SnapshotChange,
  TrackedTopic,
  WorkspaceStats,
} from '../types/api';

/** Input suggestions — plain example queries, never presented as data. */
const EXAMPLE_QUERIES = [
  'Emerging AI technologies in India',
  'Serverless database trends',
  'How is AI transforming healthcare in 2026?',
  'Rust vs Go for backend services',
];

const STATUS_META: Record<
  ResearchStatus,
  { label: string; dot: string; text: string }
> = {
  completed: { label: 'Completed', dot: 'bg-emerald-400', text: 'text-emerald-400' },
  failed: { label: 'Failed', dot: 'bg-red-400', text: 'text-red-400' },
  pending: { label: 'Pending', dot: 'bg-amber-400', text: 'text-amber-400' },
};

/** Full timestamp for tooltips (accessibility) — pairs with formatWhen(). */
function formatFull(iso: string): string {
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

/** Compact human-friendly time for list rows: Today, Yesterday, or a date. */
function formatWhen(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const now = new Date();
  const time = d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
  if (d.toDateString() === now.toDateString()) return `Today, ${time}`;
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (d.toDateString() === yesterday.toDateString()) return `Yesterday, ${time}`;
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

/** Day-only date (e.g. "Oct 10") for snapshot intervals. */
function formatDay(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

export default function Dashboard() {
  const navigate = useNavigate();
  const { push } = useToast();
  const { status, loading: configLoading } = useConfigStatus();

  const [recent, setRecent] = useState<ResearchListItem[]>([]);
  const [topics, setTopics] = useState<SavedTopic[]>([]);
  const [stats, setStats] = useState<WorkspaceStats | null>(null);
  const [activity, setActivity] = useState<ActivityPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [topicToDelete, setTopicToDelete] = useState<SavedTopic | null>(null);
  // Trend tracking — loaded independently so a trends failure never blanks
  // the rest of the dashboard (issue: failure isolation).
  const [trackedTopics, setTrackedTopics] = useState<TrackedTopic[]>([]);
  const [latestChanges, setLatestChanges] = useState<Record<string, SnapshotChange>>({});
  const [trendsLoading, setTrendsLoading] = useState(true);
  const [trendsError, setTrendsError] = useState<string | null>(null);
  // Fills the research input when an example chip is chosen (no auto-run).
  const [query, setQuery] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // No per-call catch: if the backend is unreachable the user must see
      // the error state with a retry action — not a silently empty workspace.
      const [research, saved, workspaceStats, activitySeries] = await Promise.all([
        api.listResearch(6, 0),
        api.listTopics(),
        api.getStats(),
        api.getActivity(30),
      ]);
      setRecent(research.items);
      setTopics(saved.items);
      setStats(workspaceStats);
      setActivity(activitySeries.points);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : 'Could not load your workspace data.',
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  /**
   * Tracked-topic status + latest detected change per topic — real data only:
   * snapshot counts come from GET /api/trends; change intervals from one
   * deterministic (basic-mode, no AI) timeline call per visible topic.
   * Timeline enrichment is best-effort: if it fails, the topic list still
   * renders and rows link to the full timeline instead.
   */
  const loadTrends = useCallback(async () => {
    setTrendsLoading(true);
    setTrendsError(null);
    try {
      const { items } = await api.listTrackedTopics();
      const sorted = [...items].sort((a, b) =>
        (b.lastSnapshotAt ?? '').localeCompare(a.lastSnapshotAt ?? ''),
      );
      setTrackedTopics(sorted);

      const changes: Record<string, SnapshotChange> = {};
      await Promise.all(
        sorted
          .slice(0, 3)
          .filter((t) => t.snapshotCount >= 2)
          .map(async (t) => {
            try {
              const timeline = await api.getTrendTimeline(t.id, { mode: 'basic' });
              const latest = timeline.changes[timeline.changes.length - 1];
              if (latest) changes[t.id] = latest;
            } catch {
              /* best-effort enrichment — the topic row still renders */
            }
          }),
      );
      setLatestChanges(changes);
    } catch (err) {
      setTrendsError(
        err instanceof ApiError ? err.message : 'Could not load trend tracking data.',
      );
    } finally {
      setTrendsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadTrends();
  }, [loadTrends]);

  function handleResearch(payload: ResearchRequest) {
    navigate(`/research?q=${encodeURIComponent(payload.query)}`, { state: payload });
  }

  /** Re-run a previous query in the research workspace (explicit action). */
  function revisitQuery(queryText: string) {
    navigate(`/research?q=${encodeURIComponent(queryText)}`, {
      state: { query: queryText },
    });
  }

  async function confirmDeleteTopic() {
    if (!topicToDelete) return;
    try {
      await api.deleteTopic(topicToDelete.id);
      setTopics((prev) => prev.filter((t) => t.id !== topicToDelete.id));
      push('success', 'Topic removed.');
    } catch (err) {
      push('error', err instanceof ApiError ? err.message : 'Could not remove the topic.');
    } finally {
      setTopicToDelete(null);
    }
  }

  return (
    <div className="space-y-6 animate-fadeUp">
      {/* A. Header — responsive: stacked on mobile, row on desktop */}
      <section className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="section-kicker mb-2">Workspace</p>
          <h2 className="font-display text-2xl font-semibold tracking-tight text-slateui-100 sm:text-3xl">
            Your intelligence workspace
          </h2>
          <p className="mt-1.5 max-w-xl text-sm leading-relaxed text-slateui-300">
            Explore information, compare evidence, and understand emerging topics.
          </p>
        </div>
        {status && status.demoMode && (
          <Link to="/settings" className="btn-secondary self-start text-sm sm:self-auto">
            <Settings2 size={15} aria-hidden />
            Configure live search
          </Link>
        )}
      </section>

      {/* B. KPI strip — real database totals, zero-filled while loading */}
      <section aria-label="Workspace statistics">
        <div className="panel overflow-hidden p-0">
          <div className="grid grid-cols-2 gap-px bg-slateui-700/40 lg:grid-cols-4">
            <StatCell
              icon={<FileText size={13} aria-hidden />}
              label="Research runs"
              value={loading || !stats ? null : String(stats.researchTotal)}
              hint="all time"
            />
            <StatCell
              icon={<FileCheck size={13} aria-hidden />}
              label="Reports"
              value={loading || !stats ? null : String(stats.reportsTotal)}
              hint="with a stored report"
            />
            <StatCell
              icon={<CalendarDays size={13} aria-hidden />}
              label="Last 7 days"
              value={loading || !stats ? null : String(stats.last7DaysResearch)}
              hint={
                stats
                  ? `${stats.last7DaysCompleted} completed · ${stats.researchFailed} failed overall`
                  : 'research runs this week'
              }
            />
            <StatCell
              icon={<Bookmark size={13} aria-hidden />}
              label="Saved topics"
              value={loading || !stats ? null : String(stats.savedTopics)}
              hint="tracked for follow-up"
            />
          </div>
        </div>
        <p className="mt-2 text-2xs text-slateui-500">
          Counts are real database totals for this instance only — no estimates.
        </p>
      </section>

      {/* C. Research panel — mode clarity, example queries, honest demo warning */}
      <section className="panel p-5 sm:p-6" aria-labelledby="quick-research">
        <div className="mb-4">
          <h3 id="quick-research" className="section-title">
            Start a research query
          </h3>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1.5">
            {status ? (
              <ModeBadge
                searchMode={status.demoMode ? 'demo' : 'live'}
                aiMode={status.aiConfigured ? 'llm' : 'basic'}
              />
            ) : configLoading ? (
              <span className="skeleton h-5 w-36 rounded" aria-hidden />
            ) : (
              <span className="text-xs text-slateui-500">Search status unavailable</span>
            )}
            <p className="text-xs text-slateui-400">
              {status
                ? status.demoMode
                  ? 'Mock data on example domains — not live web results.'
                  : 'Results come from live web search; every report labels its mode.'
                : ''}
            </p>
          </div>
        </div>
        {status && !status.serpapiConfigured && (
          <p className="mb-4 flex items-start gap-2 rounded-md border border-amber-400/30 bg-amber-400/10 px-3 py-2 text-xs leading-relaxed text-amber-300">
            <Info size={14} aria-hidden className="mt-0.5 shrink-0" />
            Live search is not configured yet. Add SERPAPI_API_KEY to your backend environment
            or switch to Demo Mode.
          </p>
        )}
        <ResearchForm
          onSubmit={handleResearch}
          initialQuery={query}
          maxResults={status?.maxResultsLimit ?? 10}
          showFilters={false}
        />
        <div className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1.5">
          <span className="text-2xs uppercase tracking-wider text-slateui-500">Try</span>
          {EXAMPLE_QUERIES.map((example) => (
            <button
              key={example}
              type="button"
              onClick={() => setQuery(example)}
              className="rounded-full border border-slateui-600/60 bg-midnight-850 px-3 py-1 text-2xs text-slateui-300 transition-colors hover:border-violetui-500/50 hover:text-violetui-300 focus-visible:border-violetui-500/50"
              title={`Fill the search box with: ${example}`}
            >
              {example}
            </button>
          ))}
        </div>
        <p className="mt-3 text-2xs text-slateui-500">
          Press Enter to research. Advanced filters are available on the New Research page.
        </p>
      </section>

      {error && <ErrorState message={error} onRetry={() => void load()} />}

      <div className="grid gap-6 lg:grid-cols-3">
        {/* D. Recent research — status indicators + report/re-run actions */}
        <section className="lg:col-span-2" aria-labelledby="recent-research">
          <div className="mb-3 flex items-center justify-between">
            <h3 id="recent-research" className="section-title flex items-center gap-2">
              <Clock size={16} aria-hidden className="text-slateui-400" />
              Recent research
            </h3>
            <Link to="/history" className="btn-ghost text-xs text-slateui-400">
              View all
              <ArrowRight size={13} aria-hidden />
            </Link>
          </div>

          {loading ? (
            <SkeletonList count={3} />
          ) : recent.length === 0 ? (
            <EmptyState
              icon={<Search size={22} aria-hidden />}
              title="No research yet"
              description="Run your first query above and your research history will appear here."
              action={
                <button type="button" onClick={() => navigate('/research')} className="btn-primary">
                  <Plus size={15} aria-hidden />
                  Start researching
                </button>
              }
            />
          ) : (
            <ul className="space-y-2.5">
              {recent.map((item) => {
                const statusMeta = STATUS_META[item.status];
                return (
                  <li key={item.id}>
                    <div className="panel group flex items-center gap-3 p-3.5 transition-colors hover:border-violetui-500/40 sm:gap-4 sm:p-4">
                      <span
                        className="grid h-9 w-9 shrink-0 place-items-center rounded-md border border-slateui-600/60 bg-midnight-700 text-slateui-300"
                        aria-hidden
                      >
                        <FileText size={16} />
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
                          <Link
                            to={`/report/${item.id}`}
                            className="min-w-0 max-w-full truncate font-medium text-slateui-100 transition-colors group-hover:text-violetui-300"
                            title={item.query}
                          >
                            {item.query}
                          </Link>
                          <span
                            className={`inline-flex shrink-0 items-center gap-1 text-2xs ${statusMeta.text}`}
                          >
                            <span className={`h-1.5 w-1.5 rounded-full ${statusMeta.dot}`} aria-hidden />
                            {statusMeta.label}
                          </span>
                        </div>
                        <p className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-2xs text-slateui-400">
                          <span title={formatFull(item.createdAt)}>{formatWhen(item.createdAt)}</span>
                          <span>{item.resultCount} results</span>
                          <span
                            className={
                              item.mode === 'demo' ? 'text-amber-300' : 'text-cyanui-400'
                            }
                          >
                            {item.mode === 'demo' ? 'Demo data' : 'Live search'}
                          </span>
                          {item.aiMode === 'basic' && <span>Basic analysis</span>}
                        </p>
                        {item.status === 'failed' && item.errorMessage && (
                          <p
                            className="mt-1 truncate text-2xs text-red-300/90"
                            title={item.errorMessage}
                          >
                            {item.errorMessage}
                          </p>
                        )}
                      </div>
                      <div className="flex shrink-0 items-center gap-0.5">
                        <button
                          type="button"
                          onClick={() => revisitQuery(item.query)}
                          className="btn-ghost p-2 text-slateui-500 hover:text-violetui-300"
                          aria-label={`Re-run research for "${item.query}"`}
                          title="Re-run this query in the research workspace"
                        >
                          <RotateCcw size={14} aria-hidden />
                        </button>
                        <Link
                          to={`/report/${item.id}`}
                          className="btn-ghost p-2 text-slateui-500 hover:text-violetui-300"
                          aria-label={`Open report for "${item.query}"`}
                          title="Open report"
                        >
                          <ArrowRight
                            size={16}
                            aria-hidden
                            className="transition-transform group-hover:translate-x-0.5"
                          />
                        </Link>
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        {/* E. Saved topics + F. Trend tracking (right rail) */}
        <div className="space-y-6">
          <section aria-labelledby="saved-topics">
            <div className="mb-3 flex items-center justify-between">
              <h3 id="saved-topics" className="section-title flex items-center gap-2">
                <Lightbulb size={16} aria-hidden className="text-slateui-400" />
                Saved topics
              </h3>
              <Link to="/topics" className="btn-ghost text-xs text-slateui-400">
                Manage
              </Link>
            </div>
            {topics.length === 0 ? (
              <div className="panel-subtle p-4 text-sm text-slateui-400">
                No saved topics yet.{' '}
                <Link to="/topics" className="text-violetui-300 hover:underline">
                  Save a topic
                </Link>{' '}
                to track it.
              </div>
            ) : (
              <ul className="space-y-2">
                {topics.slice(0, 5).map((t) => (
                  <li
                    key={t.id}
                    className="panel-subtle flex items-center justify-between gap-2 px-3 py-2.5 transition-colors hover:border-violetui-500/30"
                  >
                    <Link
                      to={`/research?q=${encodeURIComponent(t.topic)}`}
                      className="min-w-0 flex-1 truncate text-sm text-slateui-200 hover:text-violetui-300 transition-colors"
                      title={`Research "${t.topic}"`}
                    >
                      {t.topic}
                    </Link>
                    <button
                      type="button"
                      onClick={() => setTopicToDelete(t)}
                      className="btn-ghost -m-1 p-1.5 text-slateui-500 hover:text-red-400"
                      aria-label={`Remove saved topic ${t.topic}`}
                    >
                      <Trash2 size={14} aria-hidden />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* F. Trend tracking — real tracked-topic status + latest change intervals */}
          <section aria-labelledby="trend-tracking">
            <div className="mb-3 flex items-center justify-between">
              <h3 id="trend-tracking" className="section-title flex items-center gap-2">
                <TrendingUp size={16} aria-hidden className="text-slateui-400" />
                Trend tracking
              </h3>
              <Link to="/trends" className="btn-ghost text-xs text-slateui-400">
                Open
                <ArrowRight size={13} aria-hidden />
              </Link>
            </div>

            {trendsLoading ? (
              <div className="panel-subtle space-y-2.5 p-4" aria-busy="true">
                <span className="skeleton block h-4 w-2/3 rounded" aria-hidden />
                <span className="skeleton block h-4 w-1/2 rounded" aria-hidden />
                <span className="skeleton block h-4 w-3/5 rounded" aria-hidden />
              </div>
            ) : trendsError ? (
              <div className="panel-subtle p-4">
                <p className="text-sm leading-relaxed text-slateui-400">{trendsError}</p>
                <button
                  type="button"
                  onClick={() => void loadTrends()}
                  className="btn-ghost mt-2 text-xs text-violetui-300"
                >
                  <RotateCcw size={13} aria-hidden />
                  Retry
                </button>
              </div>
            ) : trackedTopics.length === 0 ? (
              <div className="panel-subtle p-4 text-sm text-slateui-400">
                No tracked topics yet.{' '}
                <Link to="/trends" className="text-violetui-300 hover:underline">
                  Track a query
                </Link>{' '}
                to build dated snapshots from your real research runs.
              </div>
            ) : (
              <>
                <p className="mb-2 text-2xs text-slateui-500">
                  {trackedTopics.length} tracked {trackedTopics.length === 1 ? 'topic' : 'topics'} ·{' '}
                  {trackedTopics.reduce((n, t) => n + t.snapshotCount, 0)} real snapshots ·
                  counts from this instance&rsquo;s database
                </p>
                <ul className="space-y-2">
                  {trackedTopics.slice(0, 3).map((t) => {
                    const change = latestChanges[t.id];
                    return (
                      <li
                        key={t.id}
                        className="panel-subtle px-3 py-2.5 transition-colors hover:border-violetui-500/30"
                      >
                        <Link
                          to={`/trends?topic=${encodeURIComponent(t.id)}`}
                          className="block min-w-0 truncate text-sm text-slateui-200 hover:text-violetui-300 transition-colors"
                          title={t.query}
                        >
                          {t.query}
                        </Link>
                        <p className="mt-0.5 text-2xs text-slateui-500">
                          {t.snapshotCount} {t.snapshotCount === 1 ? 'snapshot' : 'snapshots'}
                          {t.lastSnapshotAt && <> · last {formatWhen(t.lastSnapshotAt)}</>}
                        </p>
                        {change ? (
                          <p className="mt-1 text-2xs leading-relaxed text-slateui-400">
                            <span className="text-emerald-400">
                              +{change.newlyObserved.length} newly observed
                            </span>{' '}
                            ·{' '}
                            <span className="text-amber-400">
                              −{change.noLongerObserved.length} no longer observed
                            </span>{' '}
                            · sources +{change.sourceCoverage.addedCount}/−
                            {change.sourceCoverage.removedCount}
                            <span className="text-slateui-500">
                              {' '}
                              (interval {formatDay(change.fromSnapshot.createdAt)} →{' '}
                              {formatDay(change.toSnapshot.createdAt)})
                            </span>
                          </p>
                        ) : (
                          <p className="mt-1 text-2xs text-slateui-500">
                            {t.snapshotCount >= 2
                              ? 'Open the timeline to see detected changes.'
                              : 'Baseline snapshot only — nothing to compare yet.'}
                          </p>
                        )}
                      </li>
                    );
                  })}
                </ul>
                <p className="mt-2 text-2xs leading-relaxed text-slateui-500">
                  Changes compare consecutive real snapshots. Absence from a newer search is not
                  proof a finding is false.
                </p>
              </>
            )}
          </section>
        </div>
      </div>

      {/* G. Historical activity — daily counts over the last 30 days, from real rows */}
      {!loading && !error && activity.length > 0 && (
        <section aria-label="Research activity over time">
          <ActivityChart points={activity} />
        </section>
      )}

      <ConfirmDialog
        open={!!topicToDelete}
        title="Remove saved topic?"
        description={
          topicToDelete
            ? `"${topicToDelete.topic}" will be removed from your saved topics. This cannot be undone.`
            : ''
        }
        confirmLabel="Remove"
        danger
        onConfirm={() => void confirmDeleteTopic()}
        onCancel={() => setTopicToDelete(null)}
      />
    </div>
  );
}

/** One KPI cell in the stats strip. Shows a skeleton block while loading. */
function StatCell({
  icon,
  label,
  value,
  hint,
}: {
  icon: React.ReactNode;
  label: string;
  value: string | null;
  hint: string;
}) {
  return (
    <div className="bg-midnight-800 px-4 py-4 sm:px-5">
      <p className="flex items-center gap-1.5 text-2xs uppercase tracking-wider text-slateui-500">
        <span className="text-slateui-400">{icon}</span>
        {label}
      </p>
      <p className="mt-1.5 font-display text-2xl font-semibold tabular-nums text-slateui-100">
        {value ?? <span className="skeleton inline-block h-7 w-10 align-middle" aria-hidden />}
      </p>
      <p className="mt-0.5 text-2xs text-slateui-500">{hint}</p>
    </div>
  );
}
