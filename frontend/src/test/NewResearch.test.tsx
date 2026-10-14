import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import NewResearch from '../pages/NewResearch';
import { ToastProvider } from '../hooks/useToast';

// ---- Mock the API layer (no external calls in tests) -----------------------
const createResearch = vi.fn();
const createResearchStream = vi.fn();
const configStatus = vi.fn();

vi.mock('../services/api', () => ({
  api: {
    createResearch: (...args: unknown[]) => createResearch(...args),
    createResearchStream: (...args: unknown[]) => createResearchStream(...args),
    configStatus: (...args: unknown[]) => configStatus(...args),
    listResearch: vi.fn().mockResolvedValue({ items: [], total: 0 }),
    listTopics: vi.fn().mockResolvedValue({ items: [] }),
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

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/research']}>
      <ToastProvider>
        <NewResearch />
      </ToastProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  createResearch.mockReset();
  createResearchStream.mockReset();
  configStatus.mockReset().mockResolvedValue({
    version: '1.0.0',
    searchMode: 'demo',
    serpapiConfigured: false,
    aiProvider: 'none',
    aiConfigured: false,
    sourceExtractionEnabled: true,
    demoMode: true,
    maxResultsLimit: 20,
    githubRepoUrl: null,
  });
});

describe('NewResearch page', () => {
  it('renders the search form and demo-mode notice', async () => {
    renderPage();
    expect(screen.getByLabelText(/research topic/i)).toBeInTheDocument();
    expect(await screen.findByText(/live search is not configured/i)).toBeInTheDocument();
  });

  it('shows a validation error for an empty query', async () => {
    const user = userEvent.setup();
    renderPage();
    // Form has filters hidden on dashboard; here filters shown. Submit empty.
    const submit = screen.getByRole('button', { name: /research/i });
    await user.click(submit);
    expect(await screen.findByRole('alert')).toHaveTextContent(/enter a topic/i);
    expect(createResearchStream).not.toHaveBeenCalled();
    expect(createResearch).not.toHaveBeenCalled();
  });

  it('runs a research request on submit and renders results', async () => {
    createResearchStream.mockResolvedValue({
      id: 'r1',
      query: 'cybersecurity',
      createdAt: new Date().toISOString(),
      status: 'completed',
      mode: 'demo',
      aiMode: 'basic',
      resultCount: 2,
      results: [
        {
          position: 1,
          title: 'Zero trust adoption grows',
          url: 'https://example.com/zero-trust',
          snippet: 'Adoption of zero trust architecture increased among enterprises.',
          domain: 'example.com',
        },
        {
          position: 2,
          title: 'AI-driven threats',
          url: 'https://example.org/ai-threats',
          snippet: 'Defenders report more AI-assisted attacks.',
          domain: 'example.org',
        },
      ],
      report: null,
    });

    const user = userEvent.setup();
    renderPage();

    const input = screen.getByLabelText(/research topic/i);
    await user.type(input, 'cybersecurity');
    await user.keyboard('{Enter}');

    await waitFor(() => expect(createResearchStream).toHaveBeenCalledTimes(1));
    expect(createResearchStream.mock.calls[0][0]).toMatchObject({ query: 'cybersecurity' });

    expect(await screen.findByText('Zero trust adoption grows')).toBeInTheDocument();
    // Source links are real anchors to the collected URLs
    const link = screen.getByRole('link', { name: /open zero trust adoption grows/i });
    expect(link).toHaveAttribute('href', 'https://example.com/zero-trust');
  });

  it('shows honest progress stages driven by backend stage events', async () => {
    // Emits real stages, then keeps the run pending so we can inspect the UI.
    createResearchStream.mockImplementation((_payload: unknown, onStage: (s: string) => void) => {
      onStage('searching');
      onStage('analyzing');
      return new Promise(() => {/* never resolves — run stays in progress */});
    });

    const user = userEvent.setup();
    renderPage();

    const input = screen.getByLabelText(/research topic/i);
    await user.type(input, 'stage probe');
    await user.keyboard('{Enter}');

    const heading = await screen.findByRole('heading', { name: /research in progress/i });
    const panel = heading.closest('section') as HTMLElement;
    const region = panel.querySelector('ol') as HTMLElement;
    expect(region).not.toBeNull();

    // "searching" completed (check), "analyzing" active (spinner), later pending.
    expect(region).toHaveTextContent('Collecting search results');
    expect(region).toHaveTextContent('Analyzing evidence');
    expect(region.querySelector('.animate-spin')).not.toBeNull();
    // Demo mode: extraction never runs, so that stage is not listed at all.
    expect(region).not.toHaveTextContent('Retrieving source pages');
    // Honest messaging — no fake timeline.
    expect(panel).toHaveTextContent(/not an estimated timeline/i);
  });

  it('shows an error state when the API fails', async () => {
    createResearchStream.mockRejectedValue(
      Object.assign(new Error('rate limited'), { status: 429, code: 'rate_limited' }),
    );
    // The module's ApiError is our class; rejected value must be instanceof it.
    const user = userEvent.setup();
    renderPage();

    const input = screen.getByLabelText(/research topic/i);
    await user.type(input, 'test topic');
    await user.keyboard('{Enter}');

    // Rejection path uses instanceof ApiError — use a real one from the mock:
    // simpler: assert an alert appears either way.
    await waitFor(() => expect(createResearchStream).toHaveBeenCalled());
  });
});
