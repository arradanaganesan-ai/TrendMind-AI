import { ArrowUpRight, Calendar, MapPin } from 'lucide-react';
import type { SearchResult } from '../../types/api';

/**
 * Card for one normalized search result. Every field is optional in the
 * underlying data — missing dates/sources are simply not rendered.
 */
export default function ResultCard({ result }: { result: SearchResult }) {
  return (
    <article className="panel group p-4 transition-colors duration-200 hover:border-violetui-500/30">
      <div className="mb-2 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <a
            href={result.url}
            target="_blank"
            rel="noopener noreferrer nofollow"
            className="font-medium text-slateui-100 hover:text-violetui-300 transition-colors line-clamp-2"
            title={result.title}
          >
            {result.title}
          </a>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-2xs text-slateui-400">
            <span className="font-mono">{result.domain}</span>
            {result.publishedDate && (
              <span className="inline-flex items-center gap-1">
                <Calendar size={11} aria-hidden />
                {result.publishedDate}
              </span>
            )}
            {result.source && (
              <span className="inline-flex items-center gap-1">
                <MapPin size={11} aria-hidden />
                {result.source}
              </span>
            )}
            <span className="inline-flex items-center gap-1">
              <span className="tabular-nums">#{result.position}</span>
            </span>
          </div>
        </div>
        <a
          href={result.url}
          target="_blank"
          rel="noopener noreferrer nofollow"
          className="btn-ghost -m-1 p-1.5 text-slateui-400 opacity-70 group-hover:opacity-100"
          aria-label={`Open ${result.title} in a new tab`}
        >
          <ArrowUpRight size={16} aria-hidden />
        </a>
      </div>
      {result.snippet && (
        <p className="text-sm leading-relaxed text-slateui-300 line-clamp-3">{result.snippet}</p>
      )}
    </article>
  );
}
