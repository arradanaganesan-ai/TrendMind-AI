import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, FileText, History as HistoryIcon, Plus, Trash2 } from 'lucide-react';
import EmptyState from '../components/ui/EmptyState';
import ErrorState from '../components/ui/ErrorState';
import { SkeletonList } from '../components/ui/Skeletons';
import ModeBadge from '../components/ui/ModeBadge';
import ConfirmDialog from '../components/ui/ConfirmDialog';
import { useToast } from '../hooks/useToast';
import { api, ApiError } from '../services/api';
import type { ResearchListItem } from '../types/api';

const PAGE_SIZE = 12;

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

/**
 * Research history with pagination and deletion.
 * History is local to this application instance (documented in the UI).
 */
export default function History() {
  const { push } = useToast();
  const [items, setItems] = useState<ResearchListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toDelete, setToDelete] = useState<ResearchListItem | null>(null);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async (off: number) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.listResearch(PAGE_SIZE, off);
      setItems(res.items);
      setTotal(res.total);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not load research history.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(offset);
  }, [offset, load]);

  async function confirmDelete() {
    if (!toDelete) return;
    setDeleting(true);
    try {
      await api.deleteResearch(toDelete.id);
      push('success', 'Research record deleted.');
      // If we deleted the last item on a page, step back one page.
      if (items.length === 1 && offset > 0) setOffset((o) => Math.max(0, o - PAGE_SIZE));
      else await load(offset);
    } catch (err) {
      push('error', err instanceof ApiError ? err.message : 'Could not delete the record.');
    } finally {
      setDeleting(false);
      setToDelete(null);
    }
  }

  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="space-y-6 animate-fadeUp">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="section-kicker mb-2">Archive</p>
          <h2 className="font-display text-2xl font-semibold tracking-tight text-slateui-100">
            Research history
          </h2>
          <p className="mt-2 text-sm text-slateui-300">
            {loading ? 'Loading…' : `${total} record${total === 1 ? '' : 's'} stored on this instance.`}
          </p>
        </div>
        <Link to="/research" className="btn-primary">
          <Plus size={15} aria-hidden />
          New research
        </Link>
      </div>

      <p className="rounded-md border border-slateui-600/50 bg-midnight-850 px-4 py-3 text-xs leading-relaxed text-slateui-400">
        History is stored locally in this application instance’s database. It is not private per
        user — there is no per-user isolation in this version.
      </p>

      {error && <ErrorState message={error} onRetry={() => void load(offset)} />}

      {loading ? (
        <SkeletonList count={4} />
      ) : !error && items.length === 0 ? (
        <EmptyState
          icon={<HistoryIcon size={22} aria-hidden />}
          title="No research history"
          description="Completed research runs are saved here automatically so you can revisit their reports."
          action={
            <Link to="/research" className="btn-primary">
              <Plus size={15} aria-hidden />
              Start your first research
            </Link>
          }
        />
      ) : (
        <>
          <ul className="space-y-3">
            {items.map((item) => (
              <li key={item.id} className="panel group p-4 transition-colors hover:border-violetui-500/30">
                <div className="flex flex-wrap items-center gap-4">
                  <span className="grid h-9 w-9 shrink-0 place-items-center rounded-md border border-slateui-600/60 bg-midnight-700 text-slateui-300">
                    <FileText size={16} aria-hidden />
                  </span>
                  <div className="min-w-0 flex-1">
                    <Link
                      to={`/report/${item.id}`}
                      className="block truncate font-medium text-slateui-100 transition-colors hover:text-violetui-300"
                    >
                      {item.query}
                    </Link>
                    <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-2xs text-slateui-400">
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
                      <ModeBadge searchMode={item.mode} aiMode={item.aiMode} />
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    <Link
                      to={`/report/${item.id}`}
                      className="btn-ghost text-xs text-slateui-400"
                      aria-label={`Open report for ${item.query}`}
                    >
                      Open report
                      <ArrowRight size={14} aria-hidden />
                    </Link>
                    <button
                      type="button"
                      onClick={() => setToDelete(item)}
                      className="btn-ghost -m-1 p-2 text-slateui-500 hover:text-red-400"
                      aria-label={`Delete research record for ${item.query}`}
                    >
                      <Trash2 size={15} aria-hidden />
                    </button>
                  </div>
                </div>
              </li>
            ))}
          </ul>

          {totalPages > 1 && (
            <nav aria-label="History pagination" className="flex items-center justify-center gap-4">
              <button
                type="button"
                className="btn-secondary text-sm"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              >
                Previous
              </button>
              <span className="text-xs text-slateui-400 tabular-nums">
                Page {page} of {totalPages}
              </span>
              <button
                type="button"
                className="btn-secondary text-sm"
                disabled={page >= totalPages}
                onClick={() => setOffset(offset + PAGE_SIZE)}
              >
                Next
              </button>
            </nav>
          )}
        </>
      )}

      <ConfirmDialog
        open={!!toDelete}
        title="Delete research record?"
        description={
          toDelete
            ? `The record for "${toDelete.query}" and its stored report will be permanently deleted. This cannot be undone.`
            : ''
        }
        confirmLabel="Delete"
        danger
        onConfirm={() => void confirmDelete()}
        onCancel={() => setToDelete(null)}
      />
      {deleting && <span className="sr-only" role="status">Deleting…</span>}
    </div>
  );
}
