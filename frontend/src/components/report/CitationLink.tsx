import type { SourceRef } from '../../types/api';

/**
 * Clickable citation marker, e.g. [S1]. Resolves against collected sources
 * so citations can never point at URLs that were not actually retrieved.
 * If a source id is unknown, a non-link marker is rendered instead.
 */
export function CitationLink({
  sourceId,
  sources,
  className = '',
}: {
  sourceId: string;
  sources: SourceRef[];
  className?: string;
}) {
  const source = sources.find((s) => s.id === sourceId);
  if (!source) {
    return (
      <span
        className={`inline-flex items-center rounded border border-slateui-600/70 bg-midnight-700 px-1.5 py-0.5 font-mono text-2xs text-slateui-400 ${className}`}
        title="Citation could not be resolved to a collected source."
      >
        {sourceId}?
      </span>
    );
  }
  return (
    <a
      href={source.url}
      target="_blank"
      rel="noopener noreferrer nofollow"
      className={`inline-flex items-center rounded border border-violetui-500/40 bg-violetui-600/15 px-1.5 py-0.5 font-mono text-2xs font-medium text-violetui-300 transition-colors hover:bg-violetui-600/30 hover:text-violetui-300 ${className}`}
      title={`${source.title} — ${source.domain}${source.extracted ? ' (page content retrieved)' : ' (search snippet only)'}`}
      aria-label={`Citation ${sourceId}: ${source.title} on ${source.domain}`}
    >
      {sourceId}
    </a>
  );
}

/** Renders a list of citation markers. */
export function CitationList({
  sourceIds,
  sources,
}: {
  sourceIds: string[];
  sources: SourceRef[];
}) {
  if (sourceIds.length === 0) return null;
  return (
    <span className="ml-1.5 inline-flex flex-wrap gap-1 align-middle" aria-label="Supporting sources">
      {sourceIds.map((id) => (
        <CitationLink key={id} sourceId={id} sources={sources} />
      ))}
    </span>
  );
}
