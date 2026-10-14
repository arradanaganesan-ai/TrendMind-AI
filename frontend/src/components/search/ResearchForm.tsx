import { useEffect, useState } from 'react';
import { Search, SlidersHorizontal, Loader2 } from 'lucide-react';
import type { ResearchFilters, ResearchRequest } from '../../types/api';

export const MAX_QUERY_LENGTH = 300;

/** Mirrors the preferences saved by the Settings page (localStorage). */
const PREFS_KEY = 'trendmind.prefs.v1';

interface SavedPrefs {
  defaultRegion?: string;
  defaultLanguage?: string;
  defaultResultCount?: number;
}

function loadSavedPrefs(): SavedPrefs {
  try {
    const raw = localStorage.getItem(PREFS_KEY);
    if (!raw) return {};
    return JSON.parse(raw) as SavedPrefs;
  } catch {
    return {};
  }
}

interface ResearchFormProps {
  onSubmit: (payload: ResearchRequest) => void;
  loading?: boolean;
  initialQuery?: string;
  maxResults?: number;
  showFilters?: boolean;
  autoFocus?: boolean;
}

/**
 * Search input + optional filters. Filters only expose options the backend
 * actually supports (category, region, language, time range, result count).
 * Enter submits; duplicate submissions are disabled while loading.
 */
export default function ResearchForm({
  onSubmit,
  loading = false,
  initialQuery = '',
  maxResults = 10,
  showFilters = true,
  autoFocus = false,
}: ResearchFormProps) {
  const [query, setQuery] = useState(initialQuery);
  const [error, setError] = useState<string | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);
  // Default filters honor the user's saved preferences from the Settings page.
  const [filters, setFilters] = useState<ResearchFilters>(() => {
    const prefs = loadSavedPrefs();
    return {
      category: 'general',
      region: prefs.defaultRegion ?? 'us',
      language: prefs.defaultLanguage ?? 'en',
      timeRange: 'any',
      numResults: Math.min(prefs.defaultResultCount ?? 10, maxResults),
    };
  });

  // Keep the input in sync when the URL query changes while this page stays
  // mounted (e.g. a new search started from the header).
  useEffect(() => {
    setQuery(initialQuery);
    setError(null);
  }, [initialQuery]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) {
      setError('Enter a topic, question, or trend to research.');
      return;
    }
    if (trimmed.length < 2) {
      setError('Queries must be at least 2 characters long.');
      return;
    }
    if (trimmed.length > MAX_QUERY_LENGTH) {
      setError(`Queries are limited to ${MAX_QUERY_LENGTH} characters.`);
      return;
    }
    setError(null);
    onSubmit({ query: trimmed, filters: showFilters ? filters : undefined });
  }

  function setFilter<K extends keyof ResearchFilters>(key: K, value: ResearchFilters[K]) {
    setFilters((prev) => ({ ...prev, [key]: value }));
  }

  const btnLabel = loading ? 'Researching…' : 'Research';

  return (
    <form onSubmit={handleSubmit} noValidate>
      <div className="flex flex-col gap-3 sm:flex-row">
        <div className="relative flex-1">
          <label htmlFor="research-query" className="sr-only">
            Research topic
          </label>
          <Search
            size={18}
            aria-hidden
            className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slateui-400"
          />
          <input
            id="research-query"
            type="search"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              if (error) setError(null);
            }}
            placeholder="e.g. Emerging AI technologies in India"
            maxLength={MAX_QUERY_LENGTH}
            autoFocus={autoFocus}
            aria-invalid={!!error}
            aria-describedby={error ? 'research-query-error' : undefined}
            className={`input py-3 pl-12 pr-4 text-base ${error ? 'border-red-500/60' : ''}`}
            disabled={loading}
          />
        </div>
        <div className="flex gap-3">
          {showFilters && (
            <button
              type="button"
              onClick={() => setFiltersOpen((o) => !o)}
              className={`btn-secondary ${filtersOpen ? 'border-violetui-500/60 text-violetui-300' : ''}`}
              aria-expanded={filtersOpen}
              aria-controls="research-filters"
              disabled={loading}
            >
              <SlidersHorizontal size={16} aria-hidden />
              <span className="hidden sm:inline">Filters</span>
            </button>
          )}
          <button type="submit" className="btn-primary flex-1 sm:flex-none" disabled={loading}>
            {loading ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <Search size={16} aria-hidden />}
            {btnLabel}
          </button>
        </div>
      </div>

      {error && (
        <p id="research-query-error" role="alert" className="mt-2 text-sm text-red-400">
          {error}
        </p>
      )}

      {showFilters && filtersOpen && (
        <div
          id="research-filters"
          className="panel-subtle mt-4 grid grid-cols-1 gap-4 p-4 sm:grid-cols-2 lg:grid-cols-5"
        >
          <div>
            <label className="label" htmlFor="f-category">Category</label>
            <select
              id="f-category"
              className="input"
              value={filters.category}
              onChange={(e) => setFilter('category', e.target.value)}
              disabled={loading}
            >
              <option value="general">General</option>
              <option value="news">News</option>
              <option value="technology">Technology</option>
              <option value="science">Science</option>
              <option value="business">Business</option>
            </select>
          </div>
          <div>
            <label className="label" htmlFor="f-region">Region</label>
            <select
              id="f-region"
              className="input"
              value={filters.region}
              onChange={(e) => setFilter('region', e.target.value)}
              disabled={loading}
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
            <label className="label" htmlFor="f-language">Language</label>
            <select
              id="f-language"
              className="input"
              value={filters.language}
              onChange={(e) => setFilter('language', e.target.value)}
              disabled={loading}
            >
              <option value="en">English</option>
              <option value="es">Spanish</option>
              <option value="fr">French</option>
              <option value="de">German</option>
              <option value="hi">Hindi</option>
            </select>
          </div>
          <div>
            <label className="label" htmlFor="f-time">Time range</label>
            <select
              id="f-time"
              className="input"
              value={filters.timeRange}
              onChange={(e) => setFilter('timeRange', e.target.value)}
              disabled={loading}
            >
              <option value="any">Any time</option>
              <option value="day">Past day</option>
              <option value="week">Past week</option>
              <option value="month">Past month</option>
              <option value="year">Past year</option>
            </select>
          </div>
          <div>
            <label className="label" htmlFor="f-count">Results</label>
            <select
              id="f-count"
              className="input"
              value={filters.numResults}
              onChange={(e) => setFilter('numResults', Number(e.target.value))}
              disabled={loading}
            >
              {Array.from({ length: Math.min(20, maxResults) }, (_, i) => i + 1)
                .filter((n) => n <= 5 || n % 5 === 0)
                .map((n) => (
                  <option key={n} value={n}>
                    {n} results
                  </option>
                ))}
            </select>
          </div>
        </div>
      )}
    </form>
  );
}
