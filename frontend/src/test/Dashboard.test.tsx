import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Dashboard from '../pages/Dashboard';
import { ToastProvider } from '../hooks/useToast';

// ---- Mock the API layer (no external calls in tests) -----------------------
const listResearch = vi.fn();
const listTopics = vi.fn();
const getStats = vi.fn();
const getActivity = vi.fn();
const listTrackedTopics = vi.fn();
const getTrendTimeline = vi.fn();
const deleteTopic = vi.fn();

vi.mock('../services/api', () => ({
  api: {
    listResearch: (...args: unknown[]) => listResearch(...args),
    listTopics: (...args: unknown[]) => listTopics(...args),
    getStats: (...args: unknown[]) => getStats(...args),
    getActivity: (...args: unknown[]) => getActivity(...args),
    listTrackedTopics: (...args: unknown[]) => listTrackedTopics(...args),
    getTrendTimeline: (...args: unknown[]) => getTrendTimeline(...args),
    deleteTopic: (...args: unknown[]) => deleteTopic(...args),
  },
  ApiError: class ApiError extends Error {
    status: number;
    code: string;
    constructor(status: number, code: string, message: string) {
      super(message);
      this.status = status;
      this.code = code;
    }
  },
}));

const flags = vi.hoisted(() => ({ aiConfigured: false }));
vi.mock('../hooks/useConfigStatus', () => ({
  useConfigStatus: () => ({
    status: { aiConfigured: flags.aiConfigured, demoMode: false, serpapiConfigured: true },
    loading: false,
    error: null,
    reload: () => {},
  }),
}));

// Charts and the research form need browser context; assert on the data instead.
vi.mock('../components/charts/AnalyticsCharts', () => ({
  ActivityChart: () => <div data-testid="activity-chart" />,
  TrendHistoryChart: () => <div data-testid="trend-chart" />,
}));
vi.mock('../components/search/ResearchForm', () => ({
  default: () => <div data-testid="research-form" />,
}));

// ---- Fixtures (shapes mirror the backend schemas) --------------------------
const T1 = '2026-01-01T10:00:00+00:00';
const T2 = '2026-01-02T12:00:00+00:00';

const researchItem = {
  id: 'run-1',
  query: 'serverless database trends',
  createdAt: T2,
  status: 'completed',
  mode: 'live',
  resultCount: 5,
  aiMode: 'llm',
  errorMessage: null,
};

const savedTopic = { id: 'topic-a', topic: 'react server components', createdAt: T1 };

const stats = {
  researchTotal: 12,
  researchCompleted: 10,
  researchFailed: 1,
  reportsTotal: 9,
  savedTopics: 3,
  last7DaysResearch: 4,
  last7DaysCompleted: 4,
};

const trackedWithChange = {
  id: 'topic-1',
  query: 'edge computing trends',
  createdAt: T1,
  snapshotCount: 2,
  firstSnapshotAt: T1,
  lastSnapshotAt: T2,
};

const trackedBaseline = {
  id: 'topic-2',
  query: 'ai in health care',
  createdAt: T1,
  snapshotCount: 1,
  firstSnapshotAt: T1,
  lastSnapshotAt: T1,
};

function makeTimeline() {
  return {
    topic: trackedWithChange,
    snapshots: [],
    changes: [
      {
        fromSnapshot: { researchId: 'run-1', createdAt: T1, searchedAt: T1 },
        toSnapshot: { researchId: 'run-2', createdAt: T2, searchedAt: T2 },
        daysApart: 1.08,
        unchangedCount: 2,
        newlyObserved: [{ index: 1, text: 'A newly observed finding' }],
        noLongerObserved: [{ index: 2, text: 'A finding absent from the newer search' }],
        absenceCaveat: 'Absence is not proof of falsehood.',
        sourceCoverage: {
          sharedCount: 3,
          addedCount: 4,
          removedCount: 2,
          addedUrls: [],
          removedUrls: [],
          addedDomains: [],
          removedDomains: [],
        },
        themeScoreChanges: [],
        incomparableThemes: [],
      },
    ],
    methodology: { mode: 'basic', explanation: [], aiNote: null, aiSummary: null },
    singleSnapshotNote: null,
    dateFrom: null,
    dateTo: null,
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/dashboard']}>
      <ToastProvider>
        <Dashboard />
      </ToastProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  flags.aiConfigured = false;
  listResearch.mockReset().mockResolvedValue({ items: [researchItem], total: 1 });
  listTopics.mockReset().mockResolvedValue({ items: [savedTopic] });
  getStats.mockReset().mockResolvedValue(stats);
  getActivity.mockReset().mockResolvedValue({
    days: 30,
    points: [{ date: '2026-01-02', count: 2, completed: 2 }],
  });
  listTrackedTopics.mockReset().mockResolvedValue({
    items: [trackedWithChange, trackedBaseline],
  });
  getTrendTimeline.mockReset().mockResolvedValue(makeTimeline());
  deleteTopic.mockReset().mockResolvedValue(undefined);
});

describe('Dashboard — trend tracking panel', () => {
  it('shows tracked-topic status and the latest real change interval', async () => {
    renderPage();

    // Real tracked-topic status from GET /api/trends.
    expect(await screen.findByText('Trend tracking')).toBeInTheDocument();
    expect(
      screen.getByText(/2 tracked topics · 3 real snapshots/),
    ).toBeInTheDocument();
    expect(screen.getByText('ai in health care')).toBeInTheDocument();
    expect(screen.getByText('edge computing trends')).toBeInTheDocument();

    // Only topics with >= 2 snapshots are enriched (basic mode, no AI).
    expect(getTrendTimeline).toHaveBeenCalledTimes(1);
    expect(getTrendTimeline).toHaveBeenCalledWith('topic-1', { mode: 'basic' });

    // Latest change deltas, labeled honestly.
    expect(await screen.findByText(/\+1 newly observed/)).toBeInTheDocument();
    expect(screen.getByText(/−1 no longer observed/)).toBeInTheDocument();
    expect(screen.getByText(/sources \+4\/−2/)).toBeInTheDocument();

    // The absence caveat is stated up front — missing ≠ proven false.
    expect(
      screen.getByText(/Absence from a newer search is not proof a finding is false/),
    ).toBeInTheDocument();
  });

  it('links each topic row to its full timeline', async () => {
    renderPage();
    await screen.findByText('Trend tracking');
    const link = screen.getByRole('link', { name: 'edge computing trends' });
    expect(link).toHaveAttribute('href', '/trends?topic=topic-1');
  });

  it('explains a single-snapshot topic without fabricating changes', async () => {
    renderPage();
    expect(await screen.findByText(/Baseline snapshot only/)).toBeInTheDocument();
    // The baseline topic never triggers a timeline request.
    expect(getTrendTimeline).not.toHaveBeenCalledWith('topic-2', expect.anything());
  });

  it('shows the empty state when nothing is tracked', async () => {
    listTrackedTopics.mockResolvedValue({ items: [] });
    renderPage();
    expect(await screen.findByText(/No tracked topics yet/)).toBeInTheDocument();
    expect(screen.queryByText(/newly observed/)).not.toBeInTheDocument();
    expect(getTrendTimeline).not.toHaveBeenCalled();
  });

  it('isolates a trends failure — the rest of the dashboard still renders', async () => {
    listTrackedTopics.mockRejectedValue(
      new (await import('../services/api')).ApiError(
        500,
        'internal_error',
        'Trend data unavailable.',
      ),
    );
    renderPage();

    // Error + retry inside the trends panel…
    expect(await screen.findByText('Trend data unavailable.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Retry/ })).toBeInTheDocument();

    // …while real research data still renders (no blank workspace).
    expect(await screen.findByText('serverless database trends')).toBeInTheDocument();
    expect(screen.getByText('12')).toBeInTheDocument(); // researchTotal KPI
    expect(screen.getByText('3')).toBeInTheDocument(); // savedTopics KPI
  });
});

describe('Dashboard — existing workspace data', () => {
  it('renders real recent research and stats', async () => {
    renderPage();
    expect(await screen.findByText('Recent research')).toBeInTheDocument();
    expect(screen.getByText('Completed')).toBeInTheDocument();
    expect(screen.getAllByText('Live search').length).toBeGreaterThan(0);
    expect(screen.getByTestId('activity-chart')).toBeInTheDocument();
  });

  it('shows the error state when the main workspace load fails', async () => {
    listResearch.mockRejectedValue(
      new (await import('../services/api')).ApiError(
        503,
        'unavailable',
        'Could not reach the backend.',
      ),
    );
    renderPage();
    expect(await screen.findByText('Could not reach the backend.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Try again/ })).toBeInTheDocument();
  });
});
