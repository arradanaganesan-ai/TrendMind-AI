import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowLeft,
  Calendar,
  Download,
  FileJson,
  HelpCircle,
  RefreshCw,
} from 'lucide-react';
import { CitationList } from '../components/report/CitationLink';
import SourceBadge, { DomainBadge } from '../components/report/SourceBadge';
import ThemeCard from '../components/results/ThemeCard';
import {
  EvidenceCoverageChart,
  SourceDistributionChart,
  ThemeDistributionChart,
} from '../components/charts/AnalyticsCharts';
import ErrorState from '../components/ui/ErrorState';
import { SkeletonList } from '../components/ui/Skeletons';
import ModeBadge from '../components/ui/ModeBadge';
import { api, ApiError } from '../services/api';
import type { EvidenceClass, Finding, ResearchRecord, SourceRef } from '../types/api';

const EVIDENCE_META: Record<EvidenceClass, { label: string; className: string }> = {
  fact: { label: 'Retrieved information', className: 'badge-live' },
  interpretation: { label: 'AI interpretation', className: 'badge bg-violetui-600/15 text-violetui-300 border-violetui-500/30' },
  hypothesis: { label: 'Hypothesis — needs verification', className: 'badge bg-amber-400/10 text-amber-300 border-amber-400/30' },
};

function formatDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function SectionHeading({ number, title }: { number: number; title: string }) {
  return (
    <h2 className="mb-4 flex items-baseline gap-3">
      <span className="font-mono text-xs font-semibold text-violetui-400 tabular-nums">
        {String(number).padStart(2, '0')}
      </span>
      <span className="font-display text-lg font-semibold tracking-tight text-slateui-100">
        {title}
      </span>
    </h2>
  );
}

function FindingItem({ finding, sources }: { finding: Finding; sources: SourceRef[] }) {
  const meta = EVIDENCE_META[finding.evidenceClass];
  return (
    <li className="panel p-4">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className={meta.className}>{meta.label}</span>
        {finding.caveat && (
          <span className="text-2xs italic text-amber-300/90">{finding.caveat}</span>
        )}
      </div>
      <p className="text-sm leading-relaxed text-slateui-200">
        {finding.text}
        <CitationList sourceIds={finding.sourceIds} sources={sources} />
      </p>
    </li>
  );
}

export default function ReportPage() {
  const { id } = useParams<{ id: string }>();
  const [record, setRecord] = useState<ResearchRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.getResearch(id);
      setRecord(data);
      if (data.status === 'failed') {
        setError(data.errorMessage ?? 'This research run failed before a report was produced.');
      } else if (!data.report) {
        setError('No report is stored for this research record.');
      }
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.status === 404
            ? 'This research record no longer exists. It may have been deleted.'
            : err.message
          : 'Could not load the report.',
      );
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="skeleton h-6 w-48" />
        <SkeletonList count={3} />
      </div>
    );
  }

  if (error || !record?.report) {
    return (
      <div className="space-y-4">
        <Link to="/history" className="btn-ghost inline-flex text-sm text-slateui-400">
          <ArrowLeft size={15} aria-hidden />
          Back to history
        </Link>
        <ErrorState
          title="Report unavailable"
          message={error ?? 'The report could not be loaded.'}
          onRetry={() => void load()}
        />
      </div>
    );
  }

  const report = record.report;
  const { sources, methodology, coverage } = report;

  return (
    <article className="space-y-10 animate-fadeUp">
      {/* Header */}
      <header className="space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          <Link to="/history" className="btn-ghost text-sm text-slateui-400">
            <ArrowLeft size={15} aria-hidden />
            History
          </Link>
          <Link to="/research" className="btn-ghost text-sm text-slateui-400">
            <ArrowLeft size={15} aria-hidden />
            New research
          </Link>
        </div>

        <div className="panel p-5 sm:p-7">
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <ModeBadge searchMode={methodology.searchMode} aiMode={methodology.aiMode} />
            <span
              className={
                methodology.contentBasis === 'extracted'
                  ? 'badge-live'
                  : methodology.contentBasis === 'mixed'
                    ? 'badge-live'
                    : 'badge-neutral'
              }
              title={
                methodology.contentBasis === 'demo'
                  ? 'This report is built from clearly labeled demo data.'
                  : 'Content basis describes whether full pages or search snippets were analyzed.'
              }
            >
              {methodology.contentBasis === 'demo'
                ? 'Demo report'
                : methodology.contentBasis === 'extracted'
                  ? 'Full pages analyzed'
                  : methodology.contentBasis === 'mixed'
                    ? 'Mixed: pages + snippets'
                    : 'Search snippets only'}
            </span>
            <span className="badge-neutral">{methodology.resultCount} results collected</span>
          </div>

          <h1 className="font-display text-balance text-2xl font-bold leading-tight tracking-tight text-slateui-100 sm:text-3xl">
            {report.researchQuestion}
          </h1>

          <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-slateui-400">
            <span className="inline-flex items-center gap-1.5">
              <Calendar size={13} aria-hidden />
              Search performed {formatDateTime(report.searchedAt)}
            </span>
            <span>Report generated {formatDateTime(report.generatedAt)}</span>
          </div>

          <div className="mt-5 flex flex-wrap gap-3">
            <a href={api.reportMarkdownUrl(record.id)} download={`${safeFilename(record.query)}.md`} className="btn-secondary text-sm">
              <Download size={15} aria-hidden />
              Export Markdown
            </a>
            <a href={api.reportJsonUrl(record.id)} download={`${safeFilename(record.query)}.json`} className="btn-secondary text-sm">
              <FileJson size={15} aria-hidden />
              Export JSON
            </a>
            <button type="button" onClick={() => void load()} className="btn-ghost text-sm text-slateui-400">
              <RefreshCw size={15} aria-hidden />
              Reload
            </button>
          </div>
        </div>
      </header>

      {/* 1. Research question (rendered in header) + 2. Executive summary */}
      <section aria-labelledby="sec-summary">
        <SectionHeading number={1} title="Executive summary" />
        <div id="sec-summary" className="panel border-violetui-500/25 p-5 leading-relaxed text-slateui-200 sm:p-6">
          <p className="text-[15px]">{report.executiveSummary}</p>
        </div>
      </section>

      {/* 3. Key findings */}
      <section aria-labelledby="sec-findings">
        <SectionHeading number={2} title="Key findings" />
        <p id="sec-findings" className="mb-4 flex flex-wrap items-center gap-2 text-xs text-slateui-400">
          Each finding is labeled by how it is grounded:
          <span className="badge-live">Retrieved information</span>
          <span className="badge bg-violetui-600/15 text-violetui-300 border border-violetui-500/30">AI interpretation</span>
          <span className="badge bg-amber-400/10 text-amber-300 border border-amber-400/30">Hypothesis</span>
        </p>
        {report.keyFindings.length === 0 ? (
          <p className="panel p-4 text-sm text-slateui-400">
            Available sources do not provide enough evidence to support confident findings.
          </p>
        ) : (
          <ul className="space-y-3">
            {report.keyFindings.map((f, i) => (
              <FindingItem key={i} finding={f} sources={sources} />
            ))}
          </ul>
        )}
      </section>

      {/* 4. Important themes */}
      <section aria-labelledby="sec-themes">
        <SectionHeading number={3} title="Important themes" />
        <p id="sec-themes" className="mb-4 text-xs leading-relaxed text-slateui-400">
          Themes are observed in this collection of results. This is a snapshot — it is not a
          claim about global trend volume or change over time.
        </p>
        {report.themes.length === 0 ? (
          <p className="panel p-4 text-sm text-slateui-400">No recurring themes were identified.</p>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {report.themes.map((t) => (
              <ThemeCard key={t.id} theme={t} sources={sources} />
            ))}
          </div>
        )}
      </section>

      {/* 5. Evidence and source comparisons */}
      <section aria-labelledby="sec-evidence">
        <SectionHeading number={4} title="Evidence and source comparisons" />
        {report.evidenceComparison.length === 0 ? (
          <p id="sec-evidence" className="panel p-4 text-sm text-slateui-400">
            Not enough overlapping claims were found across sources for comparison.
          </p>
        ) : (
          <ul id="sec-evidence" className="space-y-3">
            {report.evidenceComparison.map((c, i) => (
              <li key={i} className="panel p-5">
                <h4 className="mb-3 font-display font-semibold text-slateui-100">{c.aspect}</h4>
                <ul className="space-y-2.5">
                  {c.claims.map((claim, j) => (
                    <li key={j} className="border-l-2 border-slateui-600 pl-3 text-sm leading-relaxed text-slateui-200">
                      {claim.claim}
                      <CitationList sourceIds={claim.sourceIds} sources={sources} />
                    </li>
                  ))}
                </ul>
                {c.note && <p className="mt-3 text-xs italic text-slateui-400">{c.note}</p>}
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* 6. Conflicting claims */}
      <section aria-labelledby="sec-conflicts">
        <SectionHeading number={5} title="Conflicting claims" />
        {report.conflictingClaims.length === 0 ? (
          <p id="sec-conflicts" className="panel p-4 text-sm text-slateui-400">
            No direct contradictions were detected among the collected sources. Absence of detected
            conflict does not mean sources agree.
          </p>
        ) : (
          <ul id="sec-conflicts" className="space-y-3">
            {report.conflictingClaims.map((c, i) => (
              <li key={i} className="panel border-amber-400/25 p-5">
                <div className="mb-3 flex items-center gap-2">
                  <AlertTriangle size={15} aria-hidden className="text-amber-400" />
                  <h4 className="font-display font-semibold text-slateui-100">{c.topic}</h4>
                </div>
                <ul className="space-y-2.5">
                  {c.positions.map((p, j) => (
                    <li key={j} className="border-l-2 border-amber-400/40 pl-3 text-sm leading-relaxed text-slateui-200">
                      {p.position}
                      <CitationList sourceIds={p.sourceIds} sources={sources} />
                    </li>
                  ))}
                </ul>
                {c.note && <p className="mt-3 text-xs italic text-slateui-400">{c.note}</p>}
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* 7. Emerging developments */}
      <section aria-labelledby="sec-developments">
        <SectionHeading number={6} title="Emerging developments" />
        {report.emergingDevelopments.length === 0 ? (
          <p id="sec-developments" className="panel p-4 text-sm text-slateui-400">
            The collected evidence does not establish clear emerging developments.
          </p>
        ) : (
          <ul id="sec-developments" className="space-y-3">
            {report.emergingDevelopments.map((f, i) => (
              <FindingItem key={i} finding={f} sources={sources} />
            ))}
          </ul>
        )}
      </section>

      {/* 8. Opportunities */}
      <section aria-labelledby="sec-opportunities">
        <SectionHeading number={7} title="Opportunities" />
        {report.opportunities.length === 0 ? (
          <p id="sec-opportunities" className="panel p-4 text-sm text-slateui-400">
            No well-supported opportunities were identified from the current evidence.
          </p>
        ) : (
          <ul id="sec-opportunities" className="space-y-3">
            {report.opportunities.map((f, i) => (
              <FindingItem key={i} finding={f} sources={sources} />
            ))}
          </ul>
        )}
      </section>

      {/* 9. Risks and limitations */}
      <section aria-labelledby="sec-risks">
        <SectionHeading number={8} title="Risks and limitations" />
        <ul id="sec-risks" className="space-y-2.5">
          {report.risksAndLimitations.length === 0 ? (
            <li className="panel p-4 text-sm text-slateui-400">
              No additional limitations were recorded for this report.
            </li>
          ) : (
            report.risksAndLimitations.map((r, i) => (
              <li
                key={i}
                className="panel flex items-start gap-3 p-4 text-sm leading-relaxed text-slateui-200"
              >
                <AlertTriangle size={15} aria-hidden className="mt-0.5 shrink-0 text-amber-400" />
                {r}
              </li>
            ))
          )}
        </ul>
      </section>

      {/* 10. Recommended follow-up questions */}
      <section aria-labelledby="sec-followup">
        <SectionHeading number={9} title="Recommended follow-up questions" />
        <ul id="sec-followup" className="grid gap-3 sm:grid-cols-2">
          {report.followUpQuestions.length === 0 ? (
            <li className="panel p-4 text-sm text-slateui-400 sm:col-span-2">
              No follow-up questions were generated for this report.
            </li>
          ) : (
            report.followUpQuestions.map((q, i) => (
              <li key={i} className="panel flex items-start gap-3 p-4">
                <HelpCircle size={15} aria-hidden className="mt-0.5 shrink-0 text-blueui-400" />
                <span className="text-sm leading-relaxed text-slateui-200">{q}</span>
              </li>
            ))
          )}
        </ul>
      </section>

      {/* Charts (real computed data) */}
      <section aria-labelledby="sec-analytics">
        <SectionHeading number={10} title="Evidence analytics" />
        <p id="sec-analytics" className="mb-4 text-xs text-slateui-400">
          All charts below are computed from this report’s collected data only.
        </p>
        <div className="grid gap-4 lg:grid-cols-3">
          <ThemeDistributionChart themes={report.themes} />
          <SourceDistributionChart sources={sources} />
          <EvidenceCoverageChart coverage={coverage} />
        </div>
      </section>

      {/* 11. Sources and references */}
      <section aria-labelledby="sec-sources">
        <SectionHeading number={11} title="Sources and references" />
        <p id="sec-sources" className="mb-4 text-xs text-slateui-400">
          {sources.length} source{sources.length === 1 ? '' : 's'} collected —{' '}
          {methodology.extractedPageCount} full page{methodology.extractedPageCount === 1 ? '' : 's'}{' '}
          retrieved, {methodology.snippetOnlyCount} snippet
          {methodology.snippetOnlyCount === 1 ? '' : 's'} only.
        </p>
        <ol className="space-y-3">
          {sources.map((s) => (
            <li key={s.id} className="panel p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="mb-1.5 flex flex-wrap items-center gap-2">
                    <span className="font-mono text-2xs font-semibold text-violetui-300">{s.id}</span>
                    <DomainBadge domain={s.domain} />
                    <SourceBadge source={s} />
                  </div>
                  <a
                    href={s.url}
                    target="_blank"
                    rel="noopener noreferrer nofollow"
                    className="font-medium text-slateui-100 hover:text-violetui-300 transition-colors"
                  >
                    {s.title}
                  </a>
                  {s.publishedDate && (
                    <p className="mt-1 text-2xs text-slateui-500">Published: {s.publishedDate}</p>
                  )}
                  <p className="mt-1.5 break-all font-mono text-2xs text-slateui-500">{s.url}</p>
                </div>
              </div>
              {s.snippet && (
                <p className="mt-2 border-t border-slateui-700/40 pt-2 text-xs leading-relaxed text-slateui-400">
                  {s.snippet}
                </p>
              )}
            </li>
          ))}
        </ol>
      </section>

      {/* 12. Research methodology */}
      <section aria-labelledby="sec-methodology">
        <SectionHeading number={12} title="Research methodology" />
        <div id="sec-methodology" className="panel p-5 sm:p-6">
          <dl className="grid gap-x-8 gap-y-3 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-2xs uppercase tracking-wider text-slateui-500">Search mode</dt>
              <dd className="text-slateui-200">
                {methodology.searchMode === 'demo'
                  ? 'Demo data (clearly labeled mock results — not live web information)'
                  : 'Live search via configured provider'}
              </dd>
            </div>
            <div>
              <dt className="text-2xs uppercase tracking-wider text-slateui-500">Analysis</dt>
              <dd className="text-slateui-200">
                {methodology.aiMode === 'llm'
                  ? 'AI-generated structured analysis (configured model)'
                  : 'Deterministic keyword-based analysis (no AI model configured — not an LLM output)'}
              </dd>
            </div>
            <div>
              <dt className="text-2xs uppercase tracking-wider text-slateui-500">Content basis</dt>
              <dd className="text-slateui-200">{contentBasisText(methodology.contentBasis)}</dd>
            </div>
            <div>
              <dt className="text-2xs uppercase tracking-wider text-slateui-500">Collected results</dt>
              <dd className="text-slateui-200 tabular-nums">{methodology.resultCount}</dd>
            </div>
            <div className="sm:col-span-2">
              <dt className="text-2xs uppercase tracking-wider text-slateui-500">
                Evidence-strength formula
              </dt>
              <dd className="mt-1 rounded-md border border-slateui-600/50 bg-midnight-900 p-3 font-mono text-xs leading-relaxed text-slateui-300">
                {methodology.scoringFormula}
              </dd>
            </div>
          </dl>
          {methodology.notes.length > 0 && (
            <ul className="mt-4 space-y-2 border-t border-slateui-700/40 pt-4">
              {methodology.notes.map((n, i) => (
                <li key={i} className="flex items-start gap-2 text-xs leading-relaxed text-slateui-400">
                  <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-slateui-500" aria-hidden />
                  {n}
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>
    </article>
  );
}

function contentBasisText(basis: string): string {
  switch (basis) {
    case 'extracted':
      return 'Full page content retrieved from accessible sources, plus search snippets';
    case 'mixed':
      return 'Mixed — some pages retrieved, remaining sources analyzed from search snippets';
    case 'demo':
      return 'Demo data (labeled mock content)';
    default:
      return 'Search snippets only — pages were not retrieved';
  }
}

/** Sanitizes user text for use in a download filename. */
export function safeFilename(query: string): string {
  const cleaned = query
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, '')
    .trim()
    .replace(/\s+/g, '-')
    .slice(0, 60);
  return `trendmind-report-${cleaned || 'research'}`;
}
