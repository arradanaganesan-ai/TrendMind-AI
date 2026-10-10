import { useEffect, useState } from 'react';
import {
  CheckCircle2,
  Database,
  KeyRound,
  Monitor,
  Moon,
  Save,
  Shield,
  Sun,
  XCircle,
} from 'lucide-react';
import ErrorState from '../components/ui/ErrorState';
import { SkeletonRows } from '../components/ui/Skeletons';
import ModeBadge from '../components/ui/ModeBadge';
import { useToast } from '../hooks/useToast';
import { useConfigStatus } from '../hooks/useConfigStatus';

interface Preferences {
  theme: 'system' | 'dark';
  defaultRegion: string;
  defaultLanguage: string;
  defaultResultCount: number;
}

const STORAGE_KEY = 'trendmind.prefs.v1';

const DEFAULT_PREFS: Preferences = {
  theme: 'system',
  defaultRegion: 'us',
  defaultLanguage: 'en',
  defaultResultCount: 10,
};

function loadPrefs(): Preferences {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_PREFS;
    const parsed = JSON.parse(raw) as Partial<Preferences>;
    return { ...DEFAULT_PREFS, ...parsed };
  } catch {
    return DEFAULT_PREFS;
  }
}

export default function Settings() {
  const { push } = useToast();
  const { status, loading, error, reload } = useConfigStatus();
  const [prefs, setPrefs] = useState<Preferences>(DEFAULT_PREFS);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    setPrefs(loadPrefs());
  }, []);

  function update<K extends keyof Preferences>(key: K, value: Preferences[K]) {
    setPrefs((p) => ({ ...p, [key]: value }));
    setDirty(true);
  }

  function save() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
      setDirty(false);
      push('success', 'Preferences saved on this device.');
    } catch {
      push('error', 'Preferences could not be saved (storage unavailable).');
    }
  }

  const appVersion = import.meta.env.VITE_APP_VERSION ?? '1.0.0';

  return (
    <div className="space-y-8 animate-fadeUp max-w-3xl">
      <div>
        <p className="section-kicker mb-2">Configuration</p>
        <h2 className="font-display text-2xl font-semibold tracking-tight text-slateui-100">
          Settings
        </h2>
        <p className="mt-2 text-sm text-slateui-300">
          Preferences are stored locally in your browser. Server credentials are configured on the
          backend — never here.
        </p>
      </div>

      {/* Search defaults */}
      <section className="panel p-5" aria-labelledby="pref-search">
        <h3 id="pref-search" className="section-title mb-4">
          Search defaults
        </h3>
        <div className="grid gap-4 sm:grid-cols-3">
          <div>
            <label className="label" htmlFor="pref-region">Default region</label>
            <select
              id="pref-region"
              className="input"
              value={prefs.defaultRegion}
              onChange={(e) => update('defaultRegion', e.target.value)}
            >
              <option value="us">United States</option>
              <option value="in">India</option>
              <option value="gb">United Kingdom</option>
              <option value="ca">Canada</option>
              <option value="au">Australia</option>
              <option value="de">Germany</option>
            </select>
          </div>
          <div>
            <label className="label" htmlFor="pref-language">Default language</label>
            <select
              id="pref-language"
              className="input"
              value={prefs.defaultLanguage}
              onChange={(e) => update('defaultLanguage', e.target.value)}
            >
              <option value="en">English</option>
              <option value="es">Spanish</option>
              <option value="fr">French</option>
              <option value="de">German</option>
              <option value="hi">Hindi</option>
            </select>
          </div>
          <div>
            <label className="label" htmlFor="pref-count">Default result count</label>
            <select
              id="pref-count"
              className="input"
              value={prefs.defaultResultCount}
              onChange={(e) => update('defaultResultCount', Number(e.target.value))}
            >
              {[5, 8, 10, 12, 15, 20].map((n) => (
                <option key={n} value={n}>
                  {n} results
                </option>
              ))}
            </select>
          </div>
        </div>
      </section>

      {/* Theme */}
      <section className="panel p-5" aria-labelledby="pref-theme">
        <h3 id="pref-theme" className="section-title mb-4">
          Theme
        </h3>
        <div className="flex flex-wrap gap-3" role="radiogroup" aria-label="Theme preference">
          {(
            [
              { value: 'system', label: 'Match system', icon: Monitor },
              { value: 'dark', label: 'Dark (default)', icon: Moon },
            ] as const
          ).map((opt) => (
            <button
              key={opt.value}
              type="button"
              role="radio"
              aria-checked={prefs.theme === opt.value}
              onClick={() => update('theme', opt.value)}
              className={`btn px-4 py-2.5 border ${
                prefs.theme === opt.value
                  ? 'border-violetui-500/70 bg-violetui-600/15 text-violetui-300'
                  : 'border-slateui-600/70 bg-midnight-700 text-slateui-300 hover:bg-midnight-600'
              }`}
            >
              <opt.icon size={15} aria-hidden />
              {opt.label}
            </button>
          ))}
          <span className="self-center text-2xs text-slateui-500">
            <Sun size={12} className="mr-1 inline" aria-hidden />
            The application ships as a dark-first design; a light theme is planned.
          </span>
        </div>
        <button type="button" onClick={save} className="btn-primary mt-4" disabled={!dirty}>
          <Save size={15} aria-hidden />
          {dirty ? 'Save preferences' : 'Saved'}
        </button>
      </section>

      {/* System status */}
      <section className="panel p-5" aria-labelledby="pref-status">
        <div className="mb-4 flex items-center justify-between gap-3">
          <h3 id="pref-status" className="section-title">
            Application status
          </h3>
          <button type="button" onClick={reload} className="btn-ghost text-xs text-slateui-400">
            Refresh
          </button>
        </div>

        {loading && <SkeletonRows rows={4} />}
        {error && <ErrorState message={error} onRetry={reload} />}

        {status && (
          <dl className="space-y-3 text-sm">
            <StatusRow
              label="Search mode"
              value={
                <ModeBadge
                  searchMode={status.demoMode ? 'demo' : 'live'}
                  aiMode={status.aiConfigured ? 'llm' : 'basic'}
                />
              }
            />
            <StatusRow
              label="SerpApi key"
              ok={status.serpapiConfigured}
              value={
                status.serpapiConfigured
                  ? 'Configured on backend (value never displayed)'
                  : 'Not configured — Demo Mode active'
              }
              icon={<KeyRound size={14} aria-hidden />}
            />
            <StatusRow
              label="AI provider"
              ok={status.aiConfigured}
              value={
                status.aiConfigured
                  ? `${status.aiProvider} — configured`
                  : 'Not configured — deterministic basic analysis used'
              }
              icon={<CheckCircle2 size={14} aria-hidden />}
            />
            <StatusRow
              label="Source extraction"
              ok={status.sourceExtractionEnabled}
              value={
                status.sourceExtractionEnabled
                  ? 'Enabled (SSRF-protected page retrieval)'
                  : 'Disabled — analysis uses search snippets only'
              }
              icon={<Shield size={14} aria-hidden />}
            />
            <StatusRow
              label="Max results per query"
              ok
              value={String(status.maxResultsLimit)}
            />
            <StatusRow
              label="Database"
              ok
              value="SQLite, local to this instance"
              icon={<Database size={14} aria-hidden />}
            />
            <StatusRow label="Application version" ok value={appVersion} />
          </dl>
        )}
      </section>

      {/* Privacy note */}
      <section className="panel p-5" aria-labelledby="pref-privacy">
        <h3 id="pref-privacy" className="section-title mb-3">
          Privacy & data storage
        </h3>
        <ul className="space-y-2.5 text-sm leading-relaxed text-slateui-300">
          <li className="flex gap-2.5">
            <XCircle size={15} aria-hidden className="mt-0.5 shrink-0 text-slateui-500" />
            No accounts or authentication — research history is shared across this instance and is
            not private per user.
          </li>
          <li className="flex gap-2.5">
            <XCircle size={15} aria-hidden className="mt-0.5 shrink-0 text-slateui-500" />
            API keys live only in backend environment variables. They are never sent to the browser
            or shown in this interface.
          </li>
          <li className="flex gap-2.5">
            <XCircle size={15} aria-hidden className="mt-0.5 shrink-0 text-slateui-500" />
            Saved preferences (region, language, result count, theme) are stored in this browser’s
            local storage only.
          </li>
          <li className="flex gap-2.5">
            <XCircle size={15} aria-hidden className="mt-0.5 shrink-0 text-slateui-500" />
            To configure keys, edit the backend <code className="font-mono text-xs">.env</code>{' '}
            file (see <code className="font-mono text-xs">.env.example</code>) and restart the
            backend — keys cannot be set from this page by design.
          </li>
        </ul>
      </section>
    </div>
  );
}

function StatusRow({
  label,
  value,
  ok,
  icon,
}: {
  label: string;
  value: React.ReactNode;
  ok?: boolean;
  icon?: React.ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slateui-700/40 pb-3 last:border-0 last:pb-0">
      <dt className="flex items-center gap-2 text-slateui-400">
        {icon}
        {label}
      </dt>
      <dd className="flex items-center gap-2 text-slateui-200">
        {typeof ok === 'boolean' &&
          (ok ? (
            <CheckCircle2 size={14} aria-hidden className="text-emerald-400" />
          ) : (
            <XCircle size={14} aria-hidden className="text-amber-400" />
          ))}
        {value}
      </dd>
    </div>
  );
}
