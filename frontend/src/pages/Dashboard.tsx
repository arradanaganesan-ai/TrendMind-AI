import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  Activity,
  ArrowRight,
  Clock,
  FileText,
  Lightbulb,
  Plus,
  Search,
  Trash2,
} from 'lucide-react';
import ResearchForm from '../components/search/ResearchForm';
import EmptyState from '../components/ui/EmptyState';
import ErrorState from '../components/ui/ErrorState';
import { SkeletonList } from '../components/ui/Skeletons';
import ModeBadge from '../components/ui/ModeBadge';
import ConfirmDialog from '../components/ui/ConfirmDialog';
import { useToast } from '../hooks/useToast';
import { useConfigStatus } from '../hooks/useConfigStatus';
import { api, ApiError } from '../services/api';
import type { ResearchListItem, ResearchRequest, SavedTopic } from '../types/api';

function formatDate(iso: string): string {
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

export default function Dashboard() {
  const navigate = useNavigate();
  const { push } = useToast();
  const { status, loading: configLoading } = useConfigStatus();

  const [recent, setRecent] = useState<ResearchListItem[]>([]);
  const [topics, setTopics] = useState<SavedTopic[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [topicToDelete, setTopicToDelete] = useState<SavedTopic | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [research, saved] = await Promise.all([
        api.listResearch(6, 0).catch(() => ({ items: [] as ResearchListItem[], total: 0 })),
        api.listTopics().catch(() => ({ items: [] as SavedTopic[] })),
      ]);
      setRecent(research.items);
      setTopics(saved.items);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'Could not load your workspace data.',
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  function handleResearch(payload: ResearchRequest) {
    navigate(`/research?q=${encodeURIComponent(payload.query)}`, { state: payload });
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

  const completedCount = recent.filter((r) => r.status === 'completed').length;
  const savedReportCount = recent.filter((r) => r.status === 'completed').length;

  return (
    <div className="space-y-8 animate-fadeUp">
      {/* A. Welcome */}
      <section>
        <p className="section-kicker mb-2">Workspace</p>
        <h2 className="font-display text-2xl font-semibold tracking-tight text-slateui-100 sm:text-3xl">
          Your intelligence workspace
        </h2>
        <p className="mt-2 text-sm leading-relaxed text-slateui-300 sm:text-base">
          Explore information, compare evidence, and understand emerging topics.
        </p>
      </section>

      {/* B. Research panel */}
      <section className="panel p-5 sm:p-6" aria-labelledby="quick-research">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 id="quick-research" className="section-title">
              Start a research query
            </h3>
            <p className="mt-1 text-xs text-slateui-400">
              Search mode:{' '}
              {status ? (
                <ModeBadge searchMode={status.demoMode ? 'demo' : 'live'} aiMode={status.aiConfigured ? 'llm' : 'basic'} />
              ) : configLoading ? (
                <span className="text-slateui-500">checking…</span>
              ) : (
                <span className="text-slateui-500">unavailable</span>
              )}
            </p>
          </div>
          {status && !status.serpapiConfigured && (
            <p className="rounded-md border border-amber-400/30 bg-amber-400/10 px-3 py-2 text-xs leading-relaxed text-amber-300">
              Live search is not configured yet. Add SERPAPI_API_KEY to your backend environment
              or switch to Demo Mode.
            </p>
          )}
        </div>
        <ResearchForm
          onSubmit={handleResearch}
          maxResults={status?.maxResultsLimit ?? 10}
          showFilters={false}
        />
        <p className="mt-3 text-2xs text-slateui-500">
          Press Enter to research. Advanced filters are available on the New Research page.
        </p>
      </section>

      {error && <ErrorState message={error} onRetry={() => void load()} />}

      <div className="grid gap-6 lg:grid-cols-3">
        {/* C. Recent research */}
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
            <ul className="space-y-3">
              {recent.map((item) => (
                <li key={item.id}>
                  <Link
                    to={`/report/${item.id}`}
                    className="panel group flex items-center gap-4 p-4 transition-colors hover:border-violetui-500/30"
                  >
                    <span className="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-midnight-700 text-slateui-300 border border-slateui-600/60">
                      <FileText size={16} aria-hidden />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium text-slateui-100 group-hover:text-violetui-300 transition-colors">
                        {item.query}
                      </p>
                      <p className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-2xs text-slateui-400">
                        <span>{formatDate(item.createdAt)}</span>
                        <span
                          className={
                            item.status === 'completed'
                              ? 'text-emerald-400'
                              : item.status === 'failed'
                                ? 'text-red-400'
                                : 'text-amber-400'
                          }
                        >
                          {item.status}
                        </span>
                        <span>{item.resultCount} results</span>
                      </p>
                    </div>
                    <ArrowRight
                      size={16}
                      aria-hidden
                      className="shrink-0 text-slateui-500 transition-transform group-hover:translate-x-0.5 group-hover:text-violetui-300"
                    />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* D + E column */}
        <div className="space-y-6">
          {/* D. Saved topics */}
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
                    className="panel-subtle flex items-center justify-between gap-2 px-3 py-2.5"
                  >
                    <Link
                      to={`/research?q=${encodeURIComponent(t.topic)}`}
                      className="min-w-0 flex-1 truncate text-sm text-slateui-200 hover:text-violetui-300 transition-colors"
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

          {/* E. Research activity — real counts from this instance only */}
          <section aria-labelledby="activity">
            <h3 id="activity" className="section-title mb-3 flex items-center gap-2">
              <Activity size={16} aria-hidden className="text-slateui-400" />
              Research activity
            </h3>
            <div className="panel divide-y divide-slateui-700/40">
              <ActivityRow
                label="Completed searches"
                value={loading ? '—' : String(completedCount)}
                hint="in recent history"
              />
              <ActivityRow
                label="Reports saved"
                value={loading ? '—' : String(savedReportCount)}
                hint="in recent history"
              />
              <ActivityRow
                label="Saved topics"
                value={loading ? '—' : String(topics.length)}
                hint="total"
              />
            </div>
            <p className="mt-2 text-2xs text-slateui-500">
              Counts are computed from this instance’s local database only.
            </p>
          </section>
        </div>
      </div>

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

function ActivityRow({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="flex items-center justify-between px-4 py-3">
      <div>
        <p className="text-sm text-slateui-200">{label}</p>
        <p className="text-2xs text-slateui-500">{hint}</p>
      </div>
      <span className="font-display text-xl font-semibold tabular-nums text-slateui-100">
        {value}
      </span>
    </div>
  );
}
