import type { AiMode, SearchMode } from '../../types/api';

interface ModeBadgeProps {
  searchMode: SearchMode;
  aiMode: AiMode;
  className?: string;
}

/**
 * Visually distinguishes live search from demo data, and LLM analysis from
 * basic deterministic analysis. Demo mode must never look like live data.
 */
export default function ModeBadge({ searchMode, aiMode, className = '' }: ModeBadgeProps) {
  const isDemo = searchMode === 'demo';
  return (
    <span className={`flex items-center gap-1.5 ${className}`}>
      <span
        className={isDemo ? 'badge-demo' : 'badge-live'}
        title={
          isDemo
            ? 'Demo mode: results are labeled mock data, not live web information.'
            : 'Live mode: results retrieved from the configured search provider.'
        }
      >
        <span
          className={`h-1.5 w-1.5 rounded-full ${isDemo ? 'bg-amber-400' : 'bg-cyanui-400'}`}
          aria-hidden
        />
        {isDemo ? 'Demo data' : 'Live search'}
      </span>
      {aiMode === 'basic' && (
        <span
          className="badge-neutral"
          title="No AI model configured: analysis is a deterministic keyword-based summary, not an LLM output."
        >
          Basic analysis
        </span>
      )}
    </span>
  );
}
