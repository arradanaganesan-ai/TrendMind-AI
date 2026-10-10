import type { ReactNode } from 'react';
import { Inbox } from 'lucide-react';

interface EmptyStateProps {
  title: string;
  description: string;
  icon?: ReactNode;
  action?: ReactNode;
}

/** Standard empty state: icon, message, and a clear next action. */
export default function EmptyState({ title, description, icon, action }: EmptyStateProps) {
  return (
    <div className="panel flex flex-col items-center justify-center px-6 py-12 text-center">
      <div className="mb-4 grid h-12 w-12 place-items-center rounded-lg border border-slateui-600/60 bg-midnight-700 text-slateui-300">
        {icon ?? <Inbox size={22} aria-hidden />}
      </div>
      <h3 className="section-title mb-1.5">{title}</h3>
      <p className="mb-5 max-w-md text-sm text-slateui-300 leading-relaxed">{description}</p>
      {action}
    </div>
  );
}
