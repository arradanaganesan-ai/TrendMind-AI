import { NavLink } from 'react-router-dom';
import {
  Compass,
  History,
  LayoutDashboard,
  Lightbulb,
  Radar,
  Settings,
  Info,
  Scale,
  TrendingUp,
} from 'lucide-react';

const NAV_ITEMS = [
  { to: '/dashboard', label: 'Overview', icon: LayoutDashboard },
  { to: '/research', label: 'New Research', icon: Radar },
  { to: '/history', label: 'Research History', icon: History },
  { to: '/compare', label: 'Compare Runs', icon: Scale },
  { to: '/trends', label: 'Trend Tracking', icon: TrendingUp },
  { to: '/topics', label: 'Saved Topics', icon: Lightbulb },
  { to: '/settings', label: 'Settings', icon: Settings },
  { to: '/about', label: 'Methodology', icon: Info },
] as const;

interface SidebarProps {
  onNavigate?: () => void;
  className?: string;
}

export default function Sidebar({ onNavigate, className = '' }: SidebarProps) {
  return (
    <nav
      aria-label="Primary"
      className={`flex h-full flex-col bg-midnight-900 border-r border-slateui-700/50 ${className}`}
    >
      <div className="flex items-center gap-2.5 px-5 h-16 border-b border-slateui-700/50 shrink-0">
        <span className="grid h-8 w-8 place-items-center rounded-md bg-gradient-to-br from-violetui-600 to-blueui-500 text-white">
          <Compass size={17} aria-hidden />
        </span>
        <div className="leading-tight">
          <p className="font-display font-semibold text-[15px] text-slateui-100">TrendMind AI</p>
          <p className="text-2xs text-slateui-400 tracking-wide">Web Intelligence Engine</p>
        </div>
      </div>

      <ul className="flex-1 space-y-1 px-3 py-4 overflow-y-auto">
        {NAV_ITEMS.map((item) => (
          <li key={item.to}>
            <NavLink
              to={item.to}
              onClick={onNavigate}
              className={({ isActive }) =>
                `group flex items-center gap-3 rounded-md px-3 py-2.5 text-sm transition-colors duration-150 ${
                  isActive
                    ? 'bg-violetui-600/15 text-violetui-300 border border-violetui-500/30'
                    : 'text-slateui-300 hover:bg-midnight-700 hover:text-slateui-100 border border-transparent'
                }`
              }
            >
              <item.icon size={17} aria-hidden className="shrink-0" />
              <span>{item.label}</span>
            </NavLink>
          </li>
        ))}
      </ul>

      <div className="px-5 py-4 border-t border-slateui-700/50">
        <p className="text-2xs text-slateui-500 leading-relaxed">
          Research history is stored locally on this application instance and is not private per
          user.
        </p>
      </div>
    </nav>
  );
}
