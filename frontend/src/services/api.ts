/**
 * TrendMind AI — API access layer.
 * All HTTP calls live here; UI components never fetch directly.
 * The backend base URL comes from VITE_API_BASE_URL (frontend/.env.local).
 * Never place server secrets in VITE_ variables.
 */
import type {
  ActivityResponse,
  ApiErrorBody,
  ConfigStatus,
  ReportComparison,
  ResearchListItem,
  ResearchRecord,
  ResearchRequest,
  ResearchStage,
  SavedTopic,
  TrackedTopic,
  TrendCandidate,
  TrendTimeline,
  WorkspaceStats,
} from '../types/api';

const BASE_URL: string = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(
  /\/+$/,
  '',
);

const DEFAULT_TIMEOUT_MS = 60_000;

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown;
  timeoutMs?: number;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, timeoutMs = DEFAULT_TIMEOUT_MS, headers, ...rest } = options;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      ...rest,
      signal: controller.signal,
      headers: {
        Accept: 'application/json',
        ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
        ...(headers ?? {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (err) {
    clearTimeout(timer);
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new ApiError(408, 'timeout', 'The request took too long and was cancelled. Please try again.');
    }
    throw new ApiError(
      0,
      'network',
      'Could not reach the TrendMind backend. Check that the server is running and the API URL is correct.',
    );
  } finally {
    clearTimeout(timer);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const text = await response.text();
  let parsed: unknown = null;
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = null;
    }
  }

  if (!response.ok) {
    const errBody = parsed as ApiErrorBody | null;
    const message =
      errBody?.error?.message ??
      fallbackMessage(response.status);
    const code = errBody?.error?.code ?? `http_${response.status}`;
    throw new ApiError(response.status, code, message);
  }

  if (parsed === null && text) {
    throw new ApiError(500, 'invalid_response', 'The server returned an unreadable response.');
  }

  return parsed as T;
}

function fallbackMessage(status: number): string {
  if (status === 404) return 'The requested record was not found.';
  if (status === 429) return 'Search capacity has temporarily been reached. Please wait before trying again.';
  if (status >= 500) return 'The server encountered a problem while processing the request.';
  return 'The request could not be completed.';
}

/** Maps error-event codes (SSE stream) back to HTTP-style statuses. */
function statusForCode(code: string): number {
  if (code === 'rate_limited') return 429;
  if (code === 'ai_unavailable') return 503;
  if (code === 'validation_error') return 422;
  return 500;
}

/**
 * Minimal SSE reader: parses `event:`/`data:` blocks from a byte stream and
 * dispatches them to `onEvent`. Only the subset the backend emits.
 */
async function readSseStream(
  body: ReadableStream<Uint8Array>,
  onEvent: (event: string, data: unknown) => void,
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let sep = buffer.indexOf('\n\n');
      while (sep !== -1) {
        const block = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        let event = 'message';
        let data = '';
        for (const line of block.split('\n')) {
          if (line.startsWith('event: ')) event = line.slice(7).trim();
          else if (line.startsWith('data: ')) data += line.slice(6);
        }
        if (data) {
          try {
            onEvent(event, JSON.parse(data));
          } catch {
            // Ignore malformed frames rather than failing the whole run.
          }
        }
        sep = buffer.indexOf('\n\n');
      }
    }
  } finally {
    reader.releaseLock();
  }
}

// ---------------------------------------------------------------------------
// Endpoints
// ---------------------------------------------------------------------------

export const api = {
  configStatus: () => request<ConfigStatus>('/api/config/status', { timeoutMs: 8_000 }),

  /** Run a research query. Long timeout: search + extraction + analysis. */
  createResearch: (payload: ResearchRequest) =>
    request<ResearchRecord>('/api/research', {
      method: 'POST',
      body: payload,
      timeoutMs: 120_000,
    }),

  /**
   * Run a research query over the SSE stream endpoint, reporting honest
   * progress stages as the backend actually reaches each pipeline step.
   *
   * Falls back to the plain POST endpoint if the stream endpoint is missing
   * (404), so a mixed-version deployment still works without progress events.
   */
  createResearchStream: async (
    payload: ResearchRequest,
    onStage: (stage: ResearchStage) => void,
  ): Promise<ResearchRecord> => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 120_000);

    let response: Response;
    try {
      response = await fetch(`${BASE_URL}/api/research/stream`, {
        method: 'POST',
        signal: controller.signal,
        headers: {
          Accept: 'text/event-stream',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });
    } catch (err) {
      clearTimeout(timer);
      if (err instanceof DOMException && err.name === 'AbortError') {
        throw new ApiError(408, 'timeout', 'The request took too long and was cancelled. Please try again.');
      }
      throw new ApiError(
        0,
        'network',
        'Could not reach the TrendMind backend. Check that the server is running and the API URL is correct.',
      );
    }

    // Stream endpoint unavailable — degrade to the classic endpoint.
    if (response.status === 404) {
      clearTimeout(timer);
      return api.createResearch(payload);
    }

    if (!response.ok) {
      clearTimeout(timer);
      const text = await response.text();
      let parsed: unknown = null;
      try {
        parsed = text ? JSON.parse(text) : null;
      } catch {
        parsed = null;
      }
      const errBody = parsed as ApiErrorBody | null;
      throw new ApiError(
        response.status,
        errBody?.error?.code ?? `http_${response.status}`,
        errBody?.error?.message ?? fallbackMessage(response.status),
      );
    }

    if (!response.body) {
      clearTimeout(timer);
      throw new ApiError(500, 'invalid_response', 'The server returned an unreadable response.');
    }

    try {
      return await new Promise<ResearchRecord>((resolve, reject) => {
        let settled = false;
        const fail = (err: ApiError) => {
          if (!settled) {
            settled = true;
            reject(err);
          }
        };

        void readSseStream(response.body as ReadableStream<Uint8Array>, (event, data) => {
          if (settled) return;
          if (event === 'stage') {
            const stage = (data as { stage?: string }).stage as ResearchStage | undefined;
            if (stage) onStage(stage);
          } else if (event === 'result') {
            settled = true;
            resolve(data as ResearchRecord);
          } else if (event === 'error') {
            const err = data as { code?: string; message?: string };
            fail(
              new ApiError(
                statusForCode(err.code ?? 'internal_error'),
                err.code ?? 'internal_error',
                err.message ?? 'The research run failed unexpectedly. Please try again.',
              ),
            );
          }
        })
          .then(() => {
            // Stream ended without a terminal event.
            fail(
              new ApiError(
                500,
                'stream_closed',
                'The connection closed before the research finished. Please try again.',
              ),
            );
          })
          .catch((err: unknown) => {
            if (err instanceof DOMException && err.name === 'AbortError') {
              fail(new ApiError(408, 'timeout', 'The request took too long and was cancelled. Please try again.'));
            } else {
              fail(
                new ApiError(0, 'network', 'The connection to the server was lost during the research run.'),
              );
            }
          });
      });
    } finally {
      clearTimeout(timer);
    }
  },

  listResearch: (limit = 20, offset = 0, filters?: { dateFrom?: string; dateTo?: string }) => {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (filters?.dateFrom) params.set('date_from', filters.dateFrom);
    if (filters?.dateTo) params.set('date_to', filters.dateTo);
    return request<{ items: ResearchListItem[]; total: number }>(
      `/api/research?${params.toString()}`,
    );
  },

  getResearch: (id: string) => request<ResearchRecord>(`/api/research/${encodeURIComponent(id)}`),

  /** Real database-backed workspace counters (totals, reports, last-7-days). */
  getStats: () => request<WorkspaceStats>('/api/stats'),

  /** Daily research activity series from real rows (zero-filled by the server). */
  getActivity: (days = 30) => request<ActivityResponse>(`/api/stats/activity?days=${days}`),

  deleteResearch: (id: string) =>
    request<void>(`/api/research/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  listTopics: () => request<{ items: SavedTopic[] }>('/api/topics'),

  addTopic: (topic: string) =>
    request<SavedTopic>('/api/topics', { method: 'POST', body: { topic } }),

  deleteTopic: (id: string) =>
    request<void>(`/api/topics/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  reportMarkdownUrl: (id: string) => `${BASE_URL}/api/reports/${encodeURIComponent(id)}/markdown`,
  reportJsonUrl: (id: string) => `${BASE_URL}/api/reports/${encodeURIComponent(id)}/json`,
  reportPdfUrl: (id: string) => `${BASE_URL}/api/reports/${encodeURIComponent(id)}/pdf`,

  /**
   * Compare two stored runs. mode=auto asks the backend to attempt an
   * AI-assisted classification; when the provider is unavailable the backend
   * returns a clearly labeled basic comparison (methodology.mode === 'basic').
   */
  compareReports: (a: string, b: string, mode: 'basic' | 'auto' = 'basic') =>
    request<ReportComparison>(
      `/api/compare?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}&mode=${mode}`,
      { timeoutMs: 90_000 },
    ),
  compareMarkdownUrl: (a: string, b: string) =>
    `${BASE_URL}/api/compare/markdown?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`,
  compareJsonUrl: (a: string, b: string) =>
    `${BASE_URL}/api/compare/json?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`,
  comparePdfUrl: (a: string, b: string) =>
    `${BASE_URL}/api/compare/pdf?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`,

  // -------------------------------------------------------------------------
  // Historical trend tracking (real dated snapshots of stored research runs)
  // -------------------------------------------------------------------------

  listTrackedTopics: () => request<{ items: TrackedTopic[] }>('/api/trends'),

  /** Distinct queries of completed runs — real options for the tracker picker. */
  trendCandidates: () => request<{ items: TrendCandidate[] }>('/api/trends/candidates'),

  /** Start tracking an existing query (idempotent; 422 when no runs exist). */
  trackTopic: (query: string) =>
    request<TrackedTopic>('/api/trends', { method: 'POST', body: { query } }),

  /**
   * Dated snapshots + consecutive change detection. mode=auto attempts one
   * bounded AI summary; on provider failure the backend returns a clearly
   * labeled basic analysis (methodology.mode === 'basic' + aiNote).
   */
  getTrendTimeline: (
    id: string,
    opts?: { dateFrom?: string; dateTo?: string; mode?: 'basic' | 'auto' },
  ) => {
    const params = new URLSearchParams();
    if (opts?.dateFrom) params.set('dateFrom', opts.dateFrom);
    if (opts?.dateTo) params.set('dateTo', opts.dateTo);
    if (opts?.mode) params.set('mode', opts.mode);
    const qs = params.toString();
    return request<TrendTimeline>(
      `/api/trends/${encodeURIComponent(id)}${qs ? `?${qs}` : ''}`,
      { timeoutMs: 90_000 },
    );
  },

  deleteTrackedTopic: (id: string) =>
    request<void>(`/api/trends/${encodeURIComponent(id)}`, { method: 'DELETE' }),
};
