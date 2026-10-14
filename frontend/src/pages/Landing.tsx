import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  ArrowRight,
  BarChart3,
  Compass,
  FileText,
  GitBranch,
  Moon,
  Search,
  ShieldCheck,
  Sparkles,
  Sun,
  Target,
} from 'lucide-react';
import { useTheme } from '../components/ui/ThemeProvider';

const EXAMPLE_CHIPS = [
  'AI & Machine Learning',
  'Technology Trends',
  'Cybersecurity',
  'Business Intelligence',
  'Future of Work',
  'Climate Technology',
];

const CAPABILITIES = [
  {
    icon: Search,
    title: 'Intelligent Search',
    text: 'Retrieve and normalize web search results through a backend search service — with filters, limits, and consistent source metadata.',
  },
  {
    icon: Target,
    title: 'Evidence-Based Analysis',
    text: 'Every source-dependent claim carries citation identifiers resolved against the sources actually collected for that query.',
  },
  {
    icon: BarChart3,
    title: 'Trend Discovery',
    text: 'Recurring themes, entities, contradictions, and evidence gaps computed from the collected results — with a documented scoring formula.',
  },
  {
    icon: FileText,
    title: 'Research Reports',
    text: 'Structured intelligence reports with executive summaries, findings, conflicts, and follow-up questions — exportable to Markdown and JSON.',
  },
];

const STEPS = [
  'Collect normalized search results for your query.',
  'Extract readable content from publicly accessible pages when safe (SSRF-protected), otherwise use search snippets.',
  'Prepare a bounded evidence package and generate structured analysis with the configured AI provider.',
  'Validate the output and verify every citation against collected sources before storage.',
];

/**
 * Public landing page. No fake logos, testimonials, or metrics —
 * only product description, capabilities, and methodology.
 */
export default function Landing() {
  const [topic, setTopic] = useState('');
  const navigate = useNavigate();
  const { resolved, toggleTheme } = useTheme();

  const repoUrl = import.meta.env.VITE_GITHUB_REPO_URL as string | undefined;

  function startResearch(q?: string) {
    const query = (q ?? topic).trim();
    navigate(query ? `/research?q=${encodeURIComponent(query)}` : '/research');
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    startResearch();
  }

  return (
    <div className="min-h-screen bg-midnight-950 text-slateui-100">
      {/* ---- Top bar ---- */}
      <header className="border-b border-slateui-700/50 bg-midnight-950/80 backdrop-blur-sm sticky top-0 z-40">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6">
          <div className="flex items-center gap-2.5">
            <span className="grid h-8 w-8 place-items-center rounded-md bg-gradient-to-br from-violetui-600 to-blueui-500 text-white">
              <Compass size={17} aria-hidden />
            </span>
            <span className="font-display font-semibold tracking-tight">TrendMind AI</span>
          </div>
          <nav aria-label="Landing" className="flex items-center gap-1 sm:gap-3">
            <button
              type="button"
              onClick={toggleTheme}
              className="btn-ghost p-2 text-slateui-400"
              aria-label={resolved === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
              title={resolved === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
            >
              {resolved === 'dark' ? <Sun size={17} aria-hidden /> : <Moon size={17} aria-hidden />}
            </button>
            <Link to="/about" className="btn-ghost text-sm text-slateui-300">
              Methodology
            </Link>
            <button type="button" onClick={() => startResearch()} className="btn-primary text-sm">
              Start Researching
            </button>
          </nav>
        </div>
      </header>

      {/* ---- Hero ---- */}
      <section className="relative overflow-hidden">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,rgba(109,74,255,0.16),transparent_55%)]"
        />
        {/* Faint engineering-grid backdrop, masked to fade out downward */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 [background-image:linear-gradient(rgba(148,163,184,0.06)_1px,transparent_1px),linear-gradient(90deg,rgba(148,163,184,0.06)_1px,transparent_1px)] [background-size:44px_44px] [mask-image:radial-gradient(ellipse_at_top,black_25%,transparent_72%)]"
        />
        <div className="relative mx-auto max-w-4xl animate-fadeUp px-4 pb-16 pt-20 text-center sm:px-6 sm:pt-28">
          <p className="section-kicker mb-5">The Web Intelligence Engine</p>
          <h1 className="font-display text-balance text-4xl font-bold leading-[1.08] tracking-tight sm:text-6xl">
            Turn the web into <span className="gradient-text">intelligence.</span>
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-balance text-base leading-relaxed text-slateui-300 sm:text-lg">
            Research emerging topics, discover recurring patterns, compare evidence, and transform
            web information into actionable insights.
          </p>

          {/* Research input */}
          <form onSubmit={handleSubmit} className="mx-auto mt-10 max-w-2xl" noValidate>
            <label htmlFor="hero-topic" className="sr-only">
              Research topic
            </label>
            <div className="panel flex items-center gap-2 p-2 pl-4 shadow-glow">
              <Search size={18} aria-hidden className="shrink-0 text-slateui-400" />
              <input
                id="hero-topic"
                type="search"
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                placeholder="Enter a topic, technology, or trend…"
                maxLength={300}
                className="min-w-0 flex-1 bg-transparent py-2.5 text-sm text-slateui-100 placeholder:text-slateui-400 focus:outline-none"
              />
              <button type="submit" className="btn-primary shrink-0">
                Research
                <ArrowRight size={15} aria-hidden />
              </button>
            </div>
          </form>

          {/* Example chips */}
          <div className="mt-5 flex flex-wrap items-center justify-center gap-2">
            <span className="text-2xs uppercase tracking-widest text-slateui-500">Try</span>
            {EXAMPLE_CHIPS.map((chip) => (
              <button
                key={chip}
                type="button"
                onClick={() => startResearch(chip)}
                className="rounded-full border border-slateui-600/70 bg-midnight-800 px-3 py-1.5 text-xs text-slateui-300 transition-colors hover:border-violetui-500/60 hover:text-violetui-300"
              >
                {chip}
              </button>
            ))}
          </div>

          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <button type="button" onClick={() => startResearch()} className="btn-primary px-6 py-3">
              Start Researching
            </button>
            <a href="#capabilities" className="btn-secondary px-6 py-3">
              Explore Capabilities
            </a>
          </div>

          {/* Honest trust chips — product traits, not invented metrics */}
          <div className="mx-auto mt-7 flex max-w-2xl flex-wrap items-center justify-center gap-x-6 gap-y-2 text-2xs text-slateui-400">
            <span className="inline-flex items-center gap-1.5">
              <ShieldCheck size={13} aria-hidden className="text-cyanui-400" />
              Every claim tied to collected sources
            </span>
            <span className="inline-flex items-center gap-1.5">
              <FileText size={13} aria-hidden className="text-violetui-400" />
              Markdown &amp; print/PDF-ready reports
            </span>
            <span className="inline-flex items-center gap-1.5">
              <Sparkles size={13} aria-hidden className="text-violetui-400" />
              Demo mode works without API keys
            </span>
          </div>
        </div>
      </section>

      {/* ---- Capabilities ---- */}
      <section id="capabilities" className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
        <div className="mb-10 text-center">
          <p className="section-kicker mb-3">Capabilities</p>
          <h2 className="font-display text-2xl font-semibold tracking-tight sm:text-3xl">
            Built for serious web research
          </h2>
        </div>
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {CAPABILITIES.map((c) => (
            <article key={c.title} className="panel p-5 transition-colors hover:border-violetui-500/30">
              <span className="mb-4 grid h-10 w-10 place-items-center rounded-md bg-violetui-600/15 text-violetui-300 border border-violetui-500/25">
                <c.icon size={19} aria-hidden />
              </span>
              <h3 className="mb-2 font-display font-semibold text-slateui-100">{c.title}</h3>
              <p className="text-sm leading-relaxed text-slateui-300">{c.text}</p>
            </article>
          ))}
        </div>
      </section>

      {/* ---- Product preview ---- */}
      <section className="border-y border-slateui-700/50 bg-midnight-900/60">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
          <div className="mb-8 text-center">
            <p className="section-kicker mb-3">Product preview</p>
            <h2 className="font-display text-2xl font-semibold tracking-tight sm:text-3xl">
              Your intelligence workspace
            </h2>
          </div>

          {/* Static, honest preview of the dashboard interface (no fabricated metrics) */}
          <div className="panel overflow-hidden" aria-label="Dashboard interface preview">
            <div className="flex items-center gap-2 border-b border-slateui-700/50 bg-midnight-850 px-4 py-2.5">
              <span className="h-2.5 w-2.5 rounded-full bg-red-400/70" aria-hidden />
              <span className="h-2.5 w-2.5 rounded-full bg-amber-400/70" aria-hidden />
              <span className="h-2.5 w-2.5 rounded-full bg-emerald-400/70" aria-hidden />
              <span className="ml-3 font-mono text-2xs text-slateui-500">trendmind — overview</span>
            </div>
            <div className="grid grid-cols-12">
              <div className="col-span-3 hidden border-r border-slateui-700/50 p-4 sm:block">
                {['Overview', 'New Research', 'Research History', 'Saved Topics', 'Settings'].map(
                  (item, i) => (
                    <div
                      key={item}
                      className={`mb-1.5 rounded px-3 py-2 text-xs ${
                        i === 0
                          ? 'bg-violetui-600/15 text-violetui-300 border border-violetui-500/30'
                          : 'text-slateui-400'
                      }`}
                    >
                      {item}
                    </div>
                  ),
                )}
              </div>
              <div className="col-span-12 space-y-4 p-4 sm:col-span-9 sm:p-6">
                <div className="rounded-md border border-slateui-600/50 bg-midnight-850 p-4">
                  <p className="mb-1 font-display text-sm font-semibold text-slateui-100">
                    Your intelligence workspace
                  </p>
                  <p className="text-xs text-slateui-400">
                    Explore information, compare evidence, and understand emerging topics.
                  </p>
                </div>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="rounded-md border border-slateui-600/50 bg-midnight-850 p-4">
                    <div className="skeleton mb-3 h-3 w-24" />
                    <div className="skeleton mb-2 h-3 w-full" />
                    <div className="skeleton h-3 w-3/5" />
                  </div>
                  <div className="rounded-md border border-slateui-600/50 bg-midnight-850 p-4">
                    <div className="skeleton mb-3 h-3 w-28" />
                    <div className="skeleton mb-2 h-3 w-full" />
                    <div className="skeleton h-3 w-4/5" />
                  </div>
                </div>
                <div className="flex items-center gap-2 rounded-md border border-dashed border-slateui-600/60 bg-midnight-850 p-4 text-xs text-slateui-500">
                  <Sparkles size={14} aria-hidden />
                  Recent research and saved topics appear here — populated by your own queries.
                </div>
              </div>
            </div>
          </div>
          <p className="mt-3 text-center text-2xs text-slateui-500">
            Preview shows the interface layout only — no usage metrics are displayed because none
            are fabricated.
          </p>
        </div>
      </section>

      {/* ---- Methodology ---- */}
      <section id="methodology" className="mx-auto max-w-4xl px-4 py-16 sm:px-6">
        <div className="mb-8 text-center">
          <p className="section-kicker mb-3">Methodology</p>
          <h2 className="font-display text-2xl font-semibold tracking-tight sm:text-3xl">
            How TrendMind works
          </h2>
          <p className="mx-auto mt-4 max-w-2xl text-sm leading-relaxed text-slateui-300">
            Search results, retrieved page content, AI-generated summaries, and unverified
            hypotheses are kept visibly distinct — so you always know what is evidenced and what is
            interpretation.
          </p>
        </div>
        <ol className="space-y-4">
          {STEPS.map((step, i) => (
            <li key={i} className="panel flex items-start gap-4 p-5">
              <span className="grid h-8 w-8 shrink-0 place-items-center rounded-md border border-violetui-500/30 bg-violetui-600/15 font-mono text-sm font-semibold text-violetui-300">
                {i + 1}
              </span>
              <p className="text-sm leading-relaxed text-slateui-200">{step}</p>
            </li>
          ))}
        </ol>
        <div className="mt-6 flex items-start gap-3 rounded-lg border border-cyanui-500/25 bg-cyanui-500/[0.05] p-4">
          <ShieldCheck size={18} aria-hidden className="mt-0.5 shrink-0 text-cyanui-400" />
          <p className="text-sm leading-relaxed text-slateui-300">
            TrendMind never invents statistics, sources, or citations. When evidence is
            insufficient, the report says so explicitly.
          </p>
        </div>
        <div className="mt-6 text-center">
          <Link to="/about" className="btn-secondary">
            Read the full methodology
            <ArrowRight size={15} aria-hidden />
          </Link>
        </div>
      </section>

      {/* ---- Footer ---- */}
      <footer className="border-t border-slateui-700/50 bg-midnight-900/60">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-6 px-4 py-10 sm:flex-row sm:px-6">
          <div className="flex items-center gap-2.5">
            <span className="grid h-8 w-8 place-items-center rounded-md bg-gradient-to-br from-violetui-600 to-blueui-500 text-white">
              <Compass size={17} aria-hidden />
            </span>
            <div>
              <p className="font-display text-sm font-semibold">TrendMind AI</p>
              <p className="text-2xs text-slateui-500">
                Search the web. Discover patterns. Understand what matters.
              </p>
            </div>
          </div>
          <nav aria-label="Footer" className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-sm text-slateui-400">
            <Link to="/about" className="transition-colors hover:text-slateui-100">
              Methodology
            </Link>
            <Link to="/about#privacy" className="transition-colors hover:text-slateui-100">
              Privacy
            </Link>
            {repoUrl && (
              <a
                href={repoUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 transition-colors hover:text-slateui-100"
              >
                <GitBranch size={14} aria-hidden />
                GitHub
              </a>
            )}
          </nav>
          <p className="text-2xs text-slateui-500">
            © {new Date().getFullYear()} TrendMind AI. All rights reserved.
          </p>
        </div>
      </footer>
    </div>
  );
}
