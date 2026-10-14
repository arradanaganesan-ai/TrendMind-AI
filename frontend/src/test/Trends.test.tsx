import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Trends from '../pages/Trends';
import { ApiError } from '../services/api';

// ---- Mock the API layer (no external calls in tests) -----------------------
const listTrackedTopics = vi.fn();
const trendCandidates = vi.fn();
const trackTopic = vi.fn();
const getTrendTimeline = vi.fn();
const deleteTrackedTopic = vi.fn();

vi.mock('../services/api', () => ({
  api: {
    listTrackedTopics: (...args: unknown[]) => listTrackedTopics(...args),
    trendCandidates: (...args: unknown[]) => trendCandidates(...args),
    trackTopic: (...args: unknown[]) => trackTopic(...args),
    getTrendTimeline: (...args: unknown[]) => getTrendTimeline(...args),
    deleteTrackedTopic: (...args: unknown[]) => deleteTrackedTopic(...args),
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
    status: { aiConfigured: flags.aiConfigured, demoMode: true },
    loading: false,
    error: null,
    reload: () => {},
  }),
}));

// The real chart needs a browser-sized container; assert on the render gate.
vi.mock('../components/charts/AnalyticsCharts', () => ({
  TrendHistoryChart: ({ snapshots }: { snapshots: { researchId: string }[] }) => (
    <div data-testid="trend-chart">{`chart-${snapshots.length}`}</div>
  ),
}));

// ---- Fixtures (shapes mirror the backend schemas) --------------------------
const T1 = '2026-01-01T10:00:00+00:00';
const T2 = '2026-01-02T12:00:00+00:00';

function makeSnapshot(id: string, at: string) {
  return {
    researchId: id,
    query: 'serverless database trends',
    createdAt: at,
    searchedAt: at,
    mode: 'demo',
    aiMode: 'basic',
    resultCount: 2,
    findingCount: 1,
    sourceCount: 1,
    domainCount: 1,
    findings: [
      { index: 0, text: `Finding for ${id}`, evidenceClass: 'fact', sourceIds: ['S1'], caveat: null },
    ],
    sources: [
      {
        id: 'S1',
        title: 'Source title',
        url: 'https://example.com/a',
        domain: 'example.com',
        snippet: 'snippet',
        publishedDate: null,
        extracted: false,
        extractionStatus: 'snippet_only',
        extractionNote: null,
      },
    ],
    themes: [{ name: 'serverless', mentionCount: 1, evidenceStrength: 55, confidence: 'moderate' }],
  };
}

function makeChange() {
  return {
    fromSnapshot: { researchId: 'run-1', createdAt: T1, searchedAt: T1 },
    toSnapshot: { researchId: 'run-2', createdAt: T2, searchedAt: T2 },
    daysApart: 1.08,
    unchangedCount: 1,
    newlyObserved: [
      { index: 1, text: 'New finding in the newer snapshot', evidenceClass: 'fact', sourceIds: ['S1'], caveat: null },
    ],
    noLongerObserved: [
      { index: 2, text: 'Finding absent from the newer search', evidenceClass: 'fact', sourceIds: ['S1'], caveat: null },
    ],
    absenceCaveat:
      '“No longer observed” means the finding did not reappear in the newer search — it is NOT evidence that the claim was proven false, retracted, or disproven.',
    sourceCoverage: {
      sharedCount: 1,
      addedCount: 1,
      removedCount: 1,
      addedUrls: ['https://example.com/new'],
      removedUrls: ['https://example.com/old'],
      addedDomains: ['new.com'],
      removedDomains: ['old.com'],
    },
    themeScoreChanges: [
      {
        theme: 'serverless',
        olderStrength: 55,
        newerStrength: 70,
        delta: 15,
        olderConfidence: 'moderate',
        newerConfidence: 'strong',
      },
    ],
    incomparableThemes: ['only-in-one'],
  };
}

function makeTimeline(
  overrides: {
    snapshots?: ReturnType<typeof makeSnapshot>[];
    methodology?: {
      mode: 'basic' | 'ai';
      explanation: string[];
      aiNote: string | null;
      aiSummary: string | null;
    };
    singleSnapshotNote?: string | null;
  } = {},
) {
  const snapshots = overrides.snapshots ?? [makeSnapshot('run-1', T1), makeSnapshot('run-2', T2)];
  return {
    topic: {
      id: 'topic-1',
      query: 'serverless database trends',
      createdAt: T1,
      snapshotCount: snapshots.length,
      firstSnapshotAt: T1,
      lastSnapshotAt: T2,
    },
    snapshots,
    changes: snapshots.length >= 2 ? [makeChange()] : [],
    methodology: overrides.methodology ?? {
      mode: 'basic',
      explanation: ['Basic trend analysis: deterministic matching only.'],
      aiNote: null,
      aiSummary: null,
    },
    singleSnapshotNote: overrides.singleSnapshotNote ?? null,
    dateFrom: null,
    dateTo: null,
  };
}

const trackedTopic = {
  id: 'topic-1',
  query: 'serverless database trends',
  createdAt: T1,
  snapshotCount: 2,
  firstSnapshotAt: T1,
  lastSnapshotAt: T2,
};

function renderPage(path = '/trends') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Trends />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  flags.aiConfigured = false;
  listTrackedTopics.mockReset().mockResolvedValue({ items: [trackedTopic] });
  trendCandidates.mockReset().mockResolvedValue({
    items: [
      {
        query: 'serverless database trends',
        runCount: 2,
        firstRunAt: T1,
        lastRunAt: T2,
      },
      {
        query: 'ai in health care',
        runCount: 5,
        firstRunAt: T1,
        lastRunAt: T2,
      },
    ],
  });
  trackTopic.mockReset().mockResolvedValue(trackedTopic);
  getTrendTimeline.mockReset().mockResolvedValue(makeTimeline());
  deleteTrackedTopic.mockReset().mockResolvedValue(undefined);
});

describe('Trends page — topic list', () => {
  it('shows tracked topics with real snapshot counts', async () => {
    renderPage();
    expect(await screen.findByText('serverless database trends')).toBeInTheDocument();
    expect(screen.getByText('2 snapshots')).toBeInTheDocument();
  });

  it('offers only untracked queries in the picker', async () => {
    renderPage();
    await screen.findByText('serverless database trends');
    expect(
      screen.getByRole('option', { name: /ai in health care/ }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('option', { name: /serverless database trends/ }),
    ).not.toBeInTheDocument();
  });

  it('tracks a topic and opens its timeline', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('serverless database trends');

    await user.selectOptions(
      screen.getByLabelText(/Track an existing research query/i),
      'ai in health care',
    );
    await user.click(screen.getByRole('button', { name: /Track topic/ }));

    expect(trackTopic).toHaveBeenCalledWith('ai in health care');
    expect(getTrendTimeline).toHaveBeenCalledWith('topic-1', {
      dateFrom: undefined,
      dateTo: undefined,
      mode: 'basic',
    });
    expect(await screen.findByText('Snapshots (oldest first)')).toBeInTheDocument();
  });

  it('deletes a topic after confirmation', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('serverless database trends');

    await user.click(screen.getByRole('button', { name: /Stop tracking/ }));
    expect(
      await screen.findByRole('button', { name: 'Untrack' }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Untrack' }));

    expect(deleteTrackedTopic).toHaveBeenCalledWith('topic-1');
    expect(await screen.findByText('No tracked topics yet')).toBeInTheDocument();
  });

  it('shows the empty state when nothing is tracked', async () => {
    listTrackedTopics.mockResolvedValue({ items: [] });
    renderPage();
    expect(await screen.findByText('No tracked topics yet')).toBeInTheDocument();
  });
});

describe('Trends page — timeline', () => {
  it('renders the chart, change detection, and the absence-not-false caveat', async () => {
    renderPage('/trends?topic=topic-1');

    // Chart only with >= 2 real snapshots.
    expect(await screen.findByTestId('trend-chart')).toHaveTextContent('chart-2');

    expect(
      await screen.findByText('Changes between consecutive snapshots (1)'),
    ).toBeInTheDocument();
    expect(screen.getByText('Newly observed (1)')).toBeInTheDocument();
    expect(screen.getByText('No longer observed (1)')).toBeInTheDocument();

    // The caveat must distinguish missing-from-newer-search from proven false.
    expect(
      screen.getByText(/NOT evidence that the claim was proven false/),
    ).toBeInTheDocument();
    expect(screen.getByText('New finding in the newer snapshot')).toBeInTheDocument();
    expect(screen.getByText('Finding absent from the newer search')).toBeInTheDocument();

    // Theme score delta and not-comparable themes.
    expect(screen.getByText('55 → 70')).toBeInTheDocument();
    expect(screen.getByText('+15')).toBeInTheDocument();
    expect(screen.getByText('only-in-one')).toBeInTheDocument();
  });

  it('hides the chart and explains a single snapshot', async () => {
    getTrendTimeline.mockResolvedValue(
      makeTimeline({
        snapshots: [makeSnapshot('run-1', T1)],
        singleSnapshotNote:
          'Only one dated snapshot exists for this topic. Change detection and the history chart appear automatically once another research run with this query is stored.',
      }),
    );
    renderPage('/trends?topic=topic-1');

    expect(
      await screen.findByText(/Only one dated snapshot exists for this topic/),
    ).toBeInTheDocument();
    expect(screen.queryByTestId('trend-chart')).not.toBeInTheDocument();
    expect(
      screen.queryByText(/Changes between consecutive snapshots/),
    ).not.toBeInTheDocument();
    // Snapshot details are still available for the single snapshot.
    expect(screen.getByText('Snapshots (oldest first)')).toBeInTheDocument();
    expect(screen.getByText('Show snapshot details')).toBeInTheDocument();
  });

  it('sends the date filters to the backend', async () => {
    renderPage('/trends?topic=topic-1');
    await screen.findByText('Snapshots (oldest first)');

    fireEvent.change(screen.getByLabelText('From'), { target: { value: '2026-01-01' } });

    expect(getTrendTimeline).toHaveBeenLastCalledWith('topic-1', {
      dateFrom: '2026-01-01',
      dateTo: undefined,
      mode: 'basic',
    });
  });

  it('requests AI mode and renders the model summary when enabled', async () => {
    flags.aiConfigured = true;
    getTrendTimeline.mockImplementation((_id: string, opts?: { mode?: string }) =>
      Promise.resolve(
        makeTimeline(
          opts?.mode === 'auto'
            ? {
                methodology: {
                  mode: 'ai',
                  explanation: ['AI-assisted summary with deterministic deltas.'],
                  aiNote: null,
                  aiSummary: 'Coverage held steady while one finding newly appeared.',
                },
              }
            : {},
        ),
      ),
    );
    const user = userEvent.setup();
    renderPage('/trends?topic=topic-1');
    await screen.findByText('Basic trend analysis');

    await user.click(screen.getByRole('checkbox'));

    expect(await screen.findByText('AI-assisted change summary')).toBeInTheDocument();
    expect(
      screen.getByText('Coverage held steady while one finding newly appeared.'),
    ).toBeInTheDocument();
    expect(getTrendTimeline).toHaveBeenLastCalledWith('topic-1', {
      dateFrom: undefined,
      dateTo: undefined,
      mode: 'auto',
    });
  });

  it('shows an honest fallback note when the AI request fails', async () => {
    flags.aiConfigured = true;
    getTrendTimeline.mockImplementation((_id: string, opts?: { mode?: string }) =>
      Promise.resolve(
        makeTimeline(
          opts?.mode === 'auto'
            ? {
                methodology: {
                  mode: 'basic',
                  explanation: ['Basic trend analysis: deterministic matching only.'],
                  aiNote:
                    'AI summary was requested, but the model was unavailable or returned invalid output. The basic deterministic change analysis is shown instead — no AI analysis was performed.',
                  aiSummary: null,
                },
              }
            : {},
        ),
      ),
    );
    const user = userEvent.setup();
    renderPage('/trends?topic=topic-1');
    await screen.findByText('Basic trend analysis');

    await user.click(screen.getByRole('checkbox'));

    expect(await screen.findByText(/no AI analysis was performed/)).toBeInTheDocument();
    expect(screen.getByText('Basic trend analysis')).toBeInTheDocument();
    // Deterministic changes are still fully present in fallback mode.
    expect(screen.getByText('Newly observed (1)')).toBeInTheDocument();
  });

  it('shows an error state when the timeline cannot be loaded', async () => {
    getTrendTimeline.mockRejectedValue(
      new ApiError(404, 'not_found', 'Tracked topic not found.'),
    );
    renderPage('/trends?topic=missing');

    expect(await screen.findByText('Timeline unavailable')).toBeInTheDocument();
    expect(screen.getByText('Tracked topic not found.')).toBeInTheDocument();
  });
});
