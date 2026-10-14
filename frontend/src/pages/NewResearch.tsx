import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams, useLocation } from 'react-router-dom';
import { ArrowRight, Info, Save, SearchX } from 'lucide-react';
import ResearchForm from '../components/search/ResearchForm';
import ResearchProgress from '../components/search/ResearchProgress';
import ResultCard from '../components/results/ResultCard';
import ErrorState from '../components/ui/ErrorState';
import EmptyState from '../components/ui/EmptyState';
import { SkeletonList } from '../components/ui/Skeletons';
import ModeBadge from '../components/ui/ModeBadge';
import { useToast } from '../hooks/useToast';
import { useConfigStatus } from '../hooks/useConfigStatus';
import { api, ApiError } from '../services/api';
import type { ResearchRecord, ResearchRequest, ResearchStage } from '../types/api';

/**
 * Search & analysis workspace. Runs a research request, then shows the
 * collected results with a link to the full report.
 * Never re-fires a request on re-render — research only runs on explicit submit.
 */
export default function NewResearch() {
  const [searchParams] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const { push } = useToast();
  const { status } = useConfigStatus();

  const [record, setRecord] = useState<ResearchRecord | null>(null);
  const [loading, setLoading] = useState(false);
  const [stage, setStage] = useState<ResearchStage | null>(null);
  const [error, setError] = useState<{ code: string; message: string } | null>(null);
  const [saved, setSaved] = useState(false);

  const urlQuery = searchParams.get('q')?.trim() ?? '';
  const statePayload = (location.state as ResearchRequest | null) ?? null;

  const runResearch = useCallback(
    async (payload: ResearchRequest) => {
      setLoading(true);
      setError(null);
      setRecord(null);
      setSaved(false);
      setStage(null);
      try {
        // SSE stream: progress stages are real backend step events.
        const result = await api.createResearchStream(payload, setStage);
        setRecord(result);
        if (result.status === 'failed') {
          setError({
            code: 'research_failed',
            message:
              result.errorMessage ??
              'The research run did not complete. Your query was not saved.',
          });
        }
      } catch (err) {
        if (err instanceof ApiError) {
          setError({ code: err.code, message: err.message });
        } else {
          setError({ code: 'unknown', message: 'The research request failed unexpectedly.' });
        }
      } finally {
        setStage(null);
        setLoading(false);
      }
    },
    [],
  );

  // Auto-run when arriving with ?q= or a dashboard payload — and re-run when
  // the query CHANGES while this page stays mounted (e.g. a second search from
  // the header). Each distinct query runs exactly once per navigation.
  const lastAutoRun = useRef<string | null>(null);
  useEffect(() => {
    const key = statePayload?.query ?? urlQuery;
    if (!key || lastAutoRun.current === key) return;
    lastAutoRun.current = key;
    void runResearch(statePayload?.query ? statePayload : { query: urlQuery });
  }, [statePayload, urlQuery, runResearch]);

  async function saveTopic() {
    if (!record) return;
    try {
      await api.addTopic(record.query);
      setSaved(true);
      push('success', 'Topic saved.');
    } catch (err) {
      push('error', err instanceof ApiError ? err.message : 'Could not save the topic.');
    }
  }

  const noResults =
    !loading && !error && record !== null && record.results.length === 0;

  return (
    <div className="space-y-6 animate-fadeUp">
      <section>
        <p className="section-kicker mb-2">Workspace</p>
        <h2 className="font-display text-2xl font-semibold tracking-tight text-slateui-100">
          New research
        </h2>
        <p className="mt-2 text-sm text-slateui-300">
          Enter a topic to collect web evidence, identify themes, and generate a structured
          report.
        </p>
      </section>

      <section className="panel p-5 sm:p-6">
        <ResearchForm
          onSubmit={(payload) => void runResearch(payload)}
          loading={loading}
          initialQuery={urlQuery}
          maxResults={status?.maxResultsLimit ?? 10}
          autoFocus={!urlQuery}
        />
        {status && !status.serpapiConfigured && (
          <p className="mt-3 flex items-start gap-2 rounded-md border border-amber-400/30 bg-amber-400/10 px-3 py-2 text-xs leading-relaxed text-amber-300">
            <Info size={14} aria-hidden className="mt-0.5 shrink-0" />
            Live search is not configured yet. Add SERPAPI_API_KEY to your backend environment or
            switch to Demo Mode.
          </p>
        )}
      </section>

      {/* Loading state — honest progress stages from the backend stream */}
      {loading && (
        <section aria-busy="true" className="space-y-4">
          <ResearchProgress
            stage={stage}
            showExtraction={Boolean(status && !status.demoMode && status.sourceExtractionEnabled)}
          />
          <SkeletonList count={3} />
        </section>
      )}

      {/* Error state — user-facing messages only */}
      {error && !loading && (
        <ErrorState
          title={error.code === 'rate_limited' ? 'Rate limit reached' : 'Research failed'}
          message={error.message}
          onRetry={
            urlQuery || statePayload
              ? () =>
                  void runResearch(
                    statePayload?.query ? statePayload : { query: urlQuery },
                  )
              : undefined
          }
        />
      )}

      {/* Empty state */}
      {noResults && (
        <EmptyState
          icon={<SearchX size={22} aria-hidden />}
          title="No results"
          description="No relevant results were returned. Try a broader query or change your search filters."
          action={
            <Link to="/history" className="btn-secondary">
              View research history
            </Link>
          }
        />
      )}

      {/* Results */}
      {record && record.results.length > 0 && !error && (
        <section className="space-y-4" aria-live="polite">
          <div className="panel p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <ModeBadge searchMode={record.mode} aiMode={record.aiMode} />
                  <span className="badge-neutral">{record.resultCount} results</span>
                </div>
                <h3 className="font-display text-lg font-semibold text-slateui-100">
                  {record.query}
                </h3>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => void saveTopic()}
                  disabled={saved}
                  className="btn-secondary text-sm"
                >
                  <Save size={15} aria-hidden />
                  {saved ? 'Topic saved' : 'Save topic'}
                </button>
                {record.status === 'completed' && (
                  <button
                    type="button"
                    onClick={() => navigate(`/report/${record.id}`)}
                    className="btn-primary text-sm"
                  >
                    Open full report
                    <ArrowRight size={15} aria-hidden />
                  </button>
                )}
              </div>
            </div>
            {record.status === 'completed' && record.report && (
              <p className="mt-3 border-t border-slateui-700/40 pt-3 text-sm leading-relaxed text-slateui-300">
                {record.report.executiveSummary}
              </p>
            )}
          </div>

          <div className="flex items-center justify-between">
            <h4 className="section-title">Collected results</h4>
            <p className="text-2xs text-slateui-500">
              Snippets are search-provider content; full pages are marked per source.
            </p>
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            {record.results.map((r) => (
              <ResultCard key={`${r.position}-${r.url}`} result={r} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
