import { AlertTriangle, RefreshCw } from 'lucide-react';

interface ErrorStateProps {
  title?: string;
  message: string;
  onRetry?: () => void;
  retryLabel?: string;
}

/**
 * Standard error state. Shows only safe, user-facing messages —
 * stack traces and credentials are never rendered.
 */
export default function ErrorState({
  title = 'Something went wrong',
  message,
  onRetry,
  retryLabel = 'Try again',
}: ErrorStateProps) {
  return (
    <div
      role="alert"
      className="panel flex flex-col items-center justify-center border-red-500/25 bg-red-500/[0.04] px-6 py-10 text-center"
    >
      <div className="mb-4 grid h-12 w-12 place-items-center rounded-lg border border-red-500/30 bg-red-500/10 text-red-400">
        <AlertTriangle size={22} aria-hidden />
      </div>
      <h3 className="mb-1.5 font-display text-base font-semibold text-slateui-100">{title}</h3>
      <p className="mb-5 max-w-md text-sm text-slateui-300 leading-relaxed">{message}</p>
      {onRetry && (
        <button type="button" onClick={onRetry} className="btn-secondary">
          <RefreshCw size={15} aria-hidden />
          {retryLabel}
        </button>
      )}
    </div>
  );
}
