import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

/**
 * Theme context — light/dark support for the design tokens.
 *
 * The user-facing preference is 'system' | 'light' | 'dark'; it is persisted
 * to localStorage and applied by setting `data-theme` on <html>, which swaps
 * the CSS variable sets declared in src/styles/index.css. Component classes
 * never change between themes — only the variables behind them.
 *
 * A small inline script in index.html applies the stored theme before first
 * paint to avoid a flash of the wrong theme.
 */

export type ThemePreference = 'system' | 'light' | 'dark';
export type ResolvedTheme = 'light' | 'dark';

const STORAGE_KEY = 'trendmind.theme.v1';

interface ThemeContextValue {
  /** Stored user preference. */
  theme: ThemePreference;
  /** Theme actually in effect after resolving 'system'. */
  resolved: ResolvedTheme;
  setTheme: (theme: ThemePreference) => void;
  /** Switches between explicit light and dark (leaves 'system'). */
  toggleTheme: () => void;
}

/** Safe defaults so useTheme() never crashes when rendered outside the provider (e.g. tests). */
const FALLBACK: ThemeContextValue = {
  theme: 'dark',
  resolved: 'dark',
  setTheme: () => {},
  toggleTheme: () => {},
};

const ThemeContext = createContext<ThemeContextValue>(FALLBACK);

function readStoredPreference(): ThemePreference {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw === 'light' || raw === 'dark' || raw === 'system') return raw;
  } catch {
    /* storage unavailable — fall back to dark */
  }
  return 'dark';
}

function systemPrefersLight(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-color-scheme: light)').matches
  );
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemePreference>(readStoredPreference);
  const [systemLight, setSystemLight] = useState<boolean>(systemPrefersLight);

  // Track system preference changes (only meaningful while theme === 'system').
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return;
    const mq = window.matchMedia('(prefers-color-scheme: light)');
    const onChange = (e: MediaQueryListEvent) => setSystemLight(e.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);

  const resolved: ResolvedTheme =
    theme === 'system' ? (systemLight ? 'light' : 'dark') : theme;

  // Apply to the document root.
  useEffect(() => {
    document.documentElement.dataset.theme = resolved;
  }, [resolved]);

  const setTheme = useCallback((next: ThemePreference) => {
    setThemeState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* preference simply won't persist */
    }
  }, []);

  const toggleTheme = useCallback(() => {
    // Toggling from 'system' resolves to the explicit opposite of current state.
    setTheme(resolved === 'dark' ? 'light' : 'dark');
  }, [resolved, setTheme]);

  const value = useMemo(
    () => ({ theme, resolved, setTheme, toggleTheme }),
    [theme, resolved, setTheme, toggleTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  return useContext(ThemeContext);
}
