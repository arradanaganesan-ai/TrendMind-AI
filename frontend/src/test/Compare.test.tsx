import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Compare from '../pages/Compare';
import { ApiError } from '../services/api';

// ---- Mock the API layer (no external calls in tests) -----------------------
const listResearch = vi.fn();
const getResearch = vi.fn();
const compareReports = vi.fn();

vi.mock('../services/api', () => ({
  api: {
    listResearch: (...args: unknown[]) => listResearch(...args),
    getResearch: (...args: unknown[]) => getResearch(...args),
    compareReports: (...args: unknown[]) => compareReports(...args),
    compareMarkdownUrl: (a: string, b: string) => `http://test/api/compare/markdown?a=${a}&b=${b}`,
    compareJsonUrl: (a: string, b: string) => `http://test/api/compare/json?a=${a}&b=${b}`,
    comparePdfUrl: (a: string, b: string) => `http://test/api/compare/pdf?a=${a}&b=${b}`,
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

vi.mock('../hooks/useConfigStatus', () => ({
  useConfigStatus: () => ({
    status: { aiConfigured: false, demoMode: true },
    loading: false,
    error: null,
    reload: () => {},
  }),
}));

// ---- Fixtures (shapes mirror the backend schemas) --------------------------
function makeRecord(id: string, query: string) {
  return {
    id,
    query,
    createdAt: '2026-01-01T10:00:00+00:00',
    status: 'completed',
    mode: 'demo',
    resultCount: 2,
    aiMode: 'basic',
    errorMessage: null,
    filters: null,
    results: [],
    report: {
      researchQuestion: query,
      executiveSummary: 'Summary.',
      keyFindings: [
        { text: 'Finding one', sourceIds: ['S1'], evidenceClass: 'fact', caveat: null },
      ],
      themes: [],
      evidenceComparison: [],
      conflictingClaims: [],
      emergingDevelopments: [],
      opportunities: [],
      risksAndLimitations: [],
      followUpQuestions: [],
      sources: [
        {
          id: 'S1',
          title: 'Shared source',
          url: 'https://example.com/x',
          domain: 'example.com',
          snippet: 'snippet',
          publishedDate: null,
          extracted: false,
          extractionStatus: 'snippet_only',
          extractionNote: null,
        },
      ],
      coverage: { supported: 1, conflicting: 0, insufficient: 0 },
      methodology: {
        searchMode: 'demo',
        aiMode: 'basic',
        contentBasis: 'demo',
        resultCount: 2,
        extractedPageCount: 0,
        snippetOnlyCount: 2,
        scoringFormula: 'formula',
        notes: [],
      },
      searchedAt: '2026-01-01T10:00:00+00:00',
      generatedAt: '2026-01-01T10:01:00+00:00',
    },
  };
}

function makeComparison() {
  const ref = (index: number) => ({
    index,
    text: 'Finding one',
    evidenceClass: 'fact',
    sourceIds: ['S1'],
    caveat: null,
  });
  return {
    runA: {
      id: 'run-a',
      query: 'query alpha',
      researchQuestion: 'Question Alpha?',
      createdAt: '2026-01-01T10:00:00+00:00',
      searchedAt: '2026-01-01T10:00:00+00:00',
      mode: 'demo',
      aiMode: 'basic',
      findingCount: 1,
      sourceCount: 1,
    },
    runB: {
      id: 'run-b',
      query: 'query beta',
      researchQuestion: 'Question Beta?',
      createdAt: '2026-01-01T12:00:00+00:00',
      searchedAt: '2026-01-01T12:00:00+00:00',
      mode: 'demo',
      aiMode: 'basic',
      findingCount: 1,
      sourceCount: 1,
    },
    sharedFindings: [
      { a: ref(0), b: ref(0), similarity: 1, matchType: 'exact', sharedSourceIds: ['S1'] },
    ],
    similarFindings: [],
    conflicts: [],
    uniqueToA: [],
    uniqueToB: [],
    sources: {
      sharedUrls: ['https://example.com/x'],
      sharedCount: 1,
      onlyACount: 0,
      onlyBCount: 0,
      sharedDomains: ['example.com'],
    },
    methodology: {
      mode: 'basic',
      explanation: [
        'Basic comparison: deterministic text matching only — no AI model was used for this comparison.',
      ],
      aiNote: null,
    },
    temporalNote: 'Both reports were searched within the same day.',
    noveltyCaveat: 'A finding that appears in only one run is not proof that it is new.',
  };
}

function renderPage(path = '/compare') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Compare />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  listResearch.mockReset().mockResolvedValue({
    items: [
      { id: 'run-a', query: 'query alpha', createdAt: '2026-01-01T10:00:00+00:00', status: 'completed', mode: 'demo', resultCount: 2, aiMode: 'basic' },
      { id: 'run-b', query: 'query beta', createdAt: '2026-01-01T12:00:00+00:00', status: 'completed', mode: 'demo', resultCount: 2, aiMode: 'basic' },
    ],
    total: 2,
  });
  getResearch.mockReset().mockImplementation((id: string) =>
    Promise.resolve(makeRecord(id, id === 'run-a' ? 'query alpha' : 'query beta')),
  );
  compareReports.mockReset().mockResolvedValue(makeComparison());
});

describe('Compare page', () => {
  it('shows the choose-two empty state initially', async () => {
    renderPage();
    expect(
      await screen.findByText('Choose two research runs'),
    ).toBeInTheDocument();
    expect(compareReports).not.toHaveBeenCalled();
  });

  it('renders the comparison sections and export links for two runs', async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByText('Choose two research runs');
    await user.selectOptions(screen.getByLabelText('Run A'), 'run-a');
    await user.selectOptions(screen.getByLabelText('Run B'), 'run-b');

    // Identity: titles, queries, dates
    expect(await screen.findByText('Question Alpha?')).toBeInTheDocument();
    expect(screen.getByText('Question Beta?')).toBeInTheDocument();
    expect(screen.getByText(/Query: “query alpha”/)).toBeInTheDocument();

    // Transparency banner (basic mode, honest wording)
    expect(await screen.findByText('Basic comparison')).toBeInTheDocument();
    expect(
      screen.getByText(/no AI model was used for this comparison/),
    ).toBeInTheDocument();

    // Sections
    expect(await screen.findByText(/Shared findings \(1\)/)).toBeInTheDocument();
    expect(screen.getByText('Exact match')).toBeInTheDocument();
    expect(screen.getByText(/Potential conflicts \(0\)/)).toBeInTheDocument();
    expect(screen.getByText(/Source differences/)).toBeInTheDocument();
    expect(screen.getByText(/not proof that it is new/)).toBeInTheDocument();

    // The comparison request used basic mode
    expect(compareReports).toHaveBeenCalledWith('run-a', 'run-b', 'basic');

    // Export links target the backend endpoints with both ids
    expect(screen.getByText('Export Markdown').closest('a')).toHaveAttribute(
      'href',
      'http://test/api/compare/markdown?a=run-a&b=run-b',
    );
    expect(screen.getByText('Export PDF').closest('a')).toHaveAttribute(
      'href',
      'http://test/api/compare/pdf?a=run-a&b=run-b',
    );
  });

  it('swaps the two runs when the Swap button is clicked', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Choose two research runs');
    await user.selectOptions(screen.getByLabelText('Run A'), 'run-a');
    await user.selectOptions(screen.getByLabelText('Run B'), 'run-b');
    await screen.findByText('Question Alpha?');

    await user.click(screen.getByRole('button', { name: 'Swap Run A and Run B' }));

    expect((screen.getByLabelText('Run A') as HTMLSelectElement).value).toBe('run-b');
    expect((screen.getByLabelText('Run B') as HTMLSelectElement).value).toBe('run-a');
    // The comparison refetches with the swapped sides
    expect(compareReports).toHaveBeenLastCalledWith('run-b', 'run-a', 'basic');
  });

  it('warns when the same run is selected on both sides', async () => {
    renderPage('/compare?a=run-a&b=run-a');
    expect(
      await screen.findByText('Pick two different research runs to compare.'),
    ).toBeInTheDocument();
    expect(compareReports).not.toHaveBeenCalled();
  });

  it('shows an error state when the comparison fails', async () => {
    compareReports.mockRejectedValue(
      new ApiError(409, 'no_report', 'This run has no stored report to compare.'),
    );
    renderPage();
    await screen.findByText('Choose two research runs');
    await userEvent.selectOptions(screen.getByLabelText('Run A'), 'run-a');
    await userEvent.selectOptions(screen.getByLabelText('Run B'), 'run-b');

    expect(await screen.findByText('Comparison unavailable')).toBeInTheDocument();
    expect(
      screen.getByText('This run has no stored report to compare.'),
    ).toBeInTheDocument();
  });
});
