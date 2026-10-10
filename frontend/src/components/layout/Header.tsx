import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Menu, Search, X } from 'lucide-react';
import ModeBadge from '../ui/ModeBadge';
import { useConfigStatus } from '../../hooks/useConfigStatus';

interface HeaderProps {
  title: string;
  onOpenMenu: () => void;
}

/**
 * Compact application header: page title, global search access, mode indicator.
 */
export default function Header({ title, onOpenMenu }: HeaderProps) {
  const [term, setTerm] = useState('');
  const navigate = useNavigate();
  const { status } = useConfigStatus();

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const q = term.trim();
    if (!q) return;
    navigate(`/research?q=${encodeURIComponent(q)}`);
    setTerm('');
  }

  return (
    <header className="sticky top-0 z-40 flex h-16 items-center gap-3 border-b border-slateui-700/50 bg-midnight-900/90 px-4 backdrop-blur-sm sm:px-6">
      <button
        type="button"
        onClick={onOpenMenu}
        className="btn-ghost lg:hidden -ml-1 p-2"
        aria-label="Open navigation menu"
      >
        <Menu size={20} aria-hidden />
      </button>

      <h1 className="font-display text-base font-semibold text-slateui-100 truncate sm:text-lg">
        {title}
      </h1>

      <div className="ml-auto flex items-center gap-2 sm:gap-3">
        <form onSubmit={submit} role="search" className="hidden md:block">
          <label htmlFor="global-search" className="sr-only">
            Global research search
          </label>
          <div className="relative">
            <Search
              size={15}
              aria-hidden
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slateui-400"
            />
            <input
              id="global-search"
              type="search"
              value={term}
              onChange={(e) => setTerm(e.target.value)}
              placeholder="Search a topic…"
              maxLength={200}
              className="input w-56 pl-9 py-2 xl:w-72"
            />
          </div>
        </form>

        {status && (
          <ModeBadge searchMode={status.demoMode ? 'demo' : 'live'} aiMode={status.aiConfigured ? 'llm' : 'basic'} />
        )}

        <Link
          to="/research"
          className="btn-primary hidden sm:inline-flex"
          title="Start a new research query"
        >
          New research
        </Link>
      </div>
    </header>
  );
}

export function CloseMenuButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="btn-ghost p-2 lg:hidden"
      aria-label="Close navigation menu"
    >
      <X size={20} aria-hidden />
    </button>
  );
}
