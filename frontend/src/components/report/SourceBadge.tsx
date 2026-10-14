import { Globe, FileText, Lock, Scissors } from 'lucide-react';
import type { SourceRef } from '../../types/api';

const STATUS_META = {
  extracted: {
    label: 'Full page retrieved',
    className: 'badge-live',
    icon: FileText,
  },
  snippet_only: {
    label: 'Search snippet only',
    className: 'badge-neutral',
    icon: Scissors,
  },
  blocked: {
    label: 'Access blocked — snippet used',
    className: 'badge bg-amber-400/10 text-amber-300 border-amber-400/30',
    icon: Lock,
  },
  failed: {
    label: 'Unreachable — snippet used',
    className: 'badge bg-amber-400/10 text-amber-300 border-amber-400/30',
    icon: Lock,
  },
  skipped: {
    label: 'Not retrieved — snippet used',
    className: 'badge-neutral',
    icon: Scissors,
  },
} as const;

/**
 * Badge describing how much of a source was actually analyzed.
 * Makes snippet-based analysis explicitly visible in the UI, including the
 * reason a page could not be retrieved (robots.txt, timeout, etc.) when the
 * backend recorded one.
 */
export default function SourceBadge({ source }: { source: SourceRef }) {
  const meta = STATUS_META[source.extractionStatus] ?? STATUS_META.snippet_only;
  const Icon = meta.icon;
  return (
    <span className="inline-flex flex-col gap-1">
      <span className={meta.className} title={source.url}>
        <Icon size={11} aria-hidden />
        {meta.label}
      </span>
      {source.extractionNote && (
        <span className="text-2xs leading-snug text-slateui-500">{source.extractionNote}</span>
      )}
    </span>
  );
}

/** Domain chip with favicon-less globe icon (no external icon requests). */
export function DomainBadge({ domain }: { domain: string }) {
  return (
    <span className="inline-flex items-center gap-1 text-2xs text-slateui-400">
      <Globe size={11} aria-hidden />
      <span className="font-mono">{domain}</span>
    </span>
  );
}
