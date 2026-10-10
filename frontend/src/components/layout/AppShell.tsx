import { useEffect, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import Sidebar from './Sidebar';
import Header from './Header';
import { X } from 'lucide-react';

/** Maps the current route to a page title for the compact header. */
const TITLES: Record<string, string> = {
  '/dashboard': 'Overview',
  '/research': 'New Research',
  '/history': 'Research History',
  '/topics': 'Saved Topics',
  '/settings': 'Settings',
  '/about': 'Methodology',
};

function titleFor(pathname: string): string {
  if (pathname.startsWith('/report/')) return 'Research Report';
  return TITLES[pathname] ?? 'TrendMind AI';
}

/**
 * Application shell: desktop sidebar, compact header, and an accessible
 * navigation drawer for tablet/mobile. Closes on route change and Escape.
 */
export default function AppShell() {
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();

  // Close the mobile drawer whenever the route changes.
  useEffect(() => {
    setMenuOpen(false);
  }, [location.pathname]);

  // Close drawer on Escape for keyboard users.
  useEffect(() => {
    if (!menuOpen) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setMenuOpen(false);
    }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [menuOpen]);

  return (
    <div className="flex min-h-screen bg-midnight-950">
      {/* Desktop sidebar */}
      <aside className="hidden w-64 shrink-0 lg:block" aria-label="Sidebar">
        <div className="fixed inset-y-0 w-64">
          <Sidebar />
        </div>
      </aside>

      {/* Mobile drawer */}
      {menuOpen && (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation menu">
          <div
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => setMenuOpen(false)}
            aria-hidden
          />
          <div className="absolute inset-y-0 left-0 w-72 max-w-[85vw] animate-fadeUp">
            <button
              type="button"
              onClick={() => setMenuOpen(false)}
              className="btn-ghost absolute right-2 top-3 z-10 p-2"
              aria-label="Close navigation menu"
            >
              <X size={20} aria-hidden />
            </button>
            <Sidebar onNavigate={() => setMenuOpen(false)} className="h-full" />
          </div>
        </div>
      )}

      {/* Main column */}
      <div className="flex min-w-0 flex-1 flex-col">
        <Header title={titleFor(location.pathname)} onOpenMenu={() => setMenuOpen(true)} />
        <main className="flex-1 px-4 py-6 sm:px-6 lg:px-8">
          <div className="mx-auto w-full max-w-7xl">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
