import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Lightbulb, Plus, Search, Trash2 } from 'lucide-react';
import EmptyState from '../components/ui/EmptyState';
import ErrorState from '../components/ui/ErrorState';
import { SkeletonList } from '../components/ui/Skeletons';
import ConfirmDialog from '../components/ui/ConfirmDialog';
import { useToast } from '../hooks/useToast';
import { api, ApiError } from '../services/api';
import type { SavedTopic } from '../types/api';

/** Saved topics: add, remove, and jump straight into research on a topic. */
export default function SavedTopics() {
  const { push } = useToast();
  const [topics, setTopics] = useState<SavedTopic[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const [adding, setAdding] = useState(false);
  const [toDelete, setToDelete] = useState<SavedTopic | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.listTopics();
      setTopics(res.items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not load saved topics.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function addTopic(e: React.FormEvent) {
    e.preventDefault();
    const topic = draft.trim();
    if (!topic) {
      push('warning', 'Enter a topic to save.');
      return;
    }
    if (topic.length > 200) {
      push('warning', 'Topics are limited to 200 characters.');
      return;
    }
    setAdding(true);
    try {
      const created = await api.addTopic(topic);
      setTopics((prev) => [created, ...prev.filter((t) => t.topic !== created.topic)]);
      setDraft('');
      push('success', 'Topic saved.');
    } catch (err) {
      push('error', err instanceof ApiError ? err.message : 'Could not save the topic.');
    } finally {
      setAdding(false);
    }
  }

  async function confirmDelete() {
    if (!toDelete) return;
    try {
      await api.deleteTopic(toDelete.id);
      setTopics((prev) => prev.filter((t) => t.id !== toDelete.id));
      push('success', 'Topic removed.');
    } catch (err) {
      push('error', err instanceof ApiError ? err.message : 'Could not remove the topic.');
    } finally {
      setToDelete(null);
    }
  }

  return (
    <div className="space-y-6 animate-fadeUp">
      <div>
        <p className="section-kicker mb-2">Watchlist</p>
        <h2 className="font-display text-2xl font-semibold tracking-tight text-slateui-100">
          Saved topics
        </h2>
        <p className="mt-2 text-sm text-slateui-300">
          Keep topics you want to research again. Select one to start a new research run.
        </p>
      </div>

      <form onSubmit={addTopic} className="panel flex flex-col gap-3 p-4 sm:flex-row" noValidate>
        <div className="flex-1">
          <label htmlFor="topic-input" className="sr-only">
            New saved topic
          </label>
          <input
            id="topic-input"
            className="input"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="e.g. Generative AI in healthcare"
            maxLength={200}
            disabled={adding}
          />
        </div>
        <button type="submit" className="btn-primary" disabled={adding}>
          <Plus size={15} aria-hidden />
          {adding ? 'Saving…' : 'Save topic'}
        </button>
      </form>

      {error && <ErrorState message={error} onRetry={() => void load()} />}

      {loading ? (
        <SkeletonList count={3} />
      ) : topics.length === 0 && !error ? (
        <EmptyState
          icon={<Lightbulb size={22} aria-hidden />}
          title="No saved topics"
          description="Save topics above to build a watchlist you can re-research at any time."
        />
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {topics.map((t) => (
            <li key={t.id} className="panel group flex flex-col justify-between p-4">
              <Link
                to={`/research?q=${encodeURIComponent(t.topic)}`}
                className="font-medium text-slateui-100 transition-colors hover:text-violetui-300"
              >
                {t.topic}
              </Link>
              <div className="mt-4 flex items-center justify-between">
                <Link
                  to={`/research?q=${encodeURIComponent(t.topic)}`}
                  className="btn-ghost text-xs text-violetui-300"
                  aria-label={`Research ${t.topic}`}
                >
                  <Search size={13} aria-hidden />
                  Research
                </Link>
                <button
                  type="button"
                  onClick={() => setToDelete(t)}
                  className="btn-ghost -m-1 p-1.5 text-slateui-500 hover:text-red-400"
                  aria-label={`Remove saved topic ${t.topic}`}
                >
                  <Trash2 size={14} aria-hidden />
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <ConfirmDialog
        open={!!toDelete}
        title="Remove saved topic?"
        description={
          toDelete ? `"${toDelete.topic}" will be removed from your saved topics.` : ''
        }
        confirmLabel="Remove"
        danger
        onConfirm={() => void confirmDelete()}
        onCancel={() => setToDelete(null)}
      />
    </div>
  );
}
