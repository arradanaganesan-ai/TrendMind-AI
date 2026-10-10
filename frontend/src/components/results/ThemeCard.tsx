import { Layers } from 'lucide-react';
import type { SourceRef, ThemeCard as ThemeCardData } from '../../types/api';
import { CitationList } from '../report/CitationLink';

const CONFIDENCE_STYLE: Record<string, string> = {
  strong: 'bg-cyanui-500/10 text-cyanui-400 border-cyanui-500/30',
  moderate: 'bg-blueui-500/10 text-blueui-300 border-blueui-500/30',
  emerging: 'bg-violetui-600/15 text-violetui-300 border-violetui-500/30',
  tentative: 'bg-slateui-600/20 text-slateui-300 border-slateui-500/40',
};

/**
 * Theme card for trend discovery output.
 * Strength is a transparent evidence score (0–100), not a probability.
 */
export default function ThemeCard({
  theme,
  sources,
}: {
  theme: ThemeCardData;
  sources: SourceRef[];
}) {
  return (
    <article className="panel flex flex-col p-4">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="flex items-center gap-2.5 min-w-0">
          <span className="grid h-8 w-8 shrink-0 place-items-center rounded-md bg-violetui-600/15 text-violetui-300 border border-violetui-500/25">
            <Layers size={15} aria-hidden />
          </span>
          <h4 className="font-display font-semibold text-slateui-100 truncate">{theme.name}</h4>
        </div>
        <span className={`badge ${CONFIDENCE_STYLE[theme.confidence] ?? CONFIDENCE_STYLE.tentative}`}>
          {theme.confidence}
        </span>
      </div>

      <p className="mb-3 flex-1 text-sm leading-relaxed text-slateui-300">{theme.description}</p>

      {/* Evidence strength meter */}
      <div className="mb-3">
        <div className="mb-1 flex items-center justify-between text-2xs text-slateui-400">
          <span>Evidence strength</span>
          <span className="tabular-nums font-medium text-slateui-200">{theme.evidenceStrength}/100</span>
        </div>
        <div
          className="h-1.5 w-full overflow-hidden rounded-full bg-midnight-700"
          role="meter"
          aria-valuenow={theme.evidenceStrength}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`Evidence strength for ${theme.name}`}
        >
          <div
            className="h-full rounded-full bg-gradient-to-r from-violetui-600 to-cyanui-500 transition-all duration-500"
            style={{ width: `${Math.max(2, Math.min(100, theme.evidenceStrength))}%` }}
          />
        </div>
        <p className="mt-1.5 text-2xs text-slateui-400">
          Mentioned by{' '}
          <span className="font-medium text-slateui-200 tabular-nums">{theme.mentionCount}</span>{' '}
          collected source{theme.mentionCount === 1 ? '' : 's'}
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-1 border-t border-slateui-700/40 pt-3">
        <span className="mr-1 text-2xs text-slateui-500">Sources:</span>
        <CitationList sourceIds={theme.sourceIds} sources={sources} />
      </div>

      {theme.limitations && (
        <p className="mt-2 text-2xs leading-relaxed text-slateui-400 border-l-2 border-amber-400/40 pl-2">
          {theme.limitations}
        </p>
      )}
    </article>
  );
}
