/**
 * TrendMind AI — API access layer.
 * All HTTP calls live here; UI components never fetch directly.
 * The backend base URL comes from VITE_API_BASE_URL (frontend/.env.local).
 * Never place server secrets in VITE_ variables.
 */
import type {
  ApiErrorBody,
  ConfigStatus,
  HealthResponse,
  ResearchListItem,
  ResearchRecord,
  ResearchRequest,
  SavedTopic,
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

// ---------------------------------------------------------------------------
// Endpoints
// ---------------------------------------------------------------------------

export const api = {
  health: () => request<HealthResponse>('/api/health', { timeoutMs: 8_000 }),

  configStatus: () => request<ConfigStatus>('/api/config/status', { timeoutMs: 8_000 }),

  /** Run a research query. Long timeout: search + extraction + analysis. */
  createResearch: (payload: ResearchRequest) =>
    request<ResearchRecord>('/api/research', {
      method: 'POST',
      body: payload,
      timeoutMs: 120_000,
    }),

  listResearch: (limit = 20, offset = 0) =>
    request<{ items: ResearchListItem[]; total: number }>(
      `/api/research?limit=${limit}&offset=${offset}`,
    ),

  getResearch: (id: string) => request<ResearchRecord>(`/api/research/${encodeURIComponent(id)}`),

  deleteResearch: (id: string) =>
    request<void>(`/api/research/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  listTopics: () => request<{ items: SavedTopic[] }>('/api/topics'),

  addTopic: (topic: string) =>
    request<SavedTopic>('/api/topics', { method: 'POST', body: { topic } }),

  deleteTopic: (id: string) =>
    request<void>(`/api/topics/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  reportMarkdownUrl: (id: string) => `${BASE_URL}/api/reports/${encodeURIComponent(id)}/markdown`,
  reportJsonUrl: (id: string) => `${BASE_URL}/api/reports/${encodeURIComponent(id)}/json`,

  /** Fetch report text (used for preview/export without leaving the SPA). */
  fetchReportMarkdown: (id: string) =>
    fetchText(`${BASE_URL}/api/reports/${encodeURIComponent(id)}/markdown`),
};

async function fetchText(url: string): Promise<string> {
  let response: Response;
  try {
    response = await fetch(url, { headers: { Accept: 'text/markdown, text/plain' } });
  } catch {
    throw new ApiError(0, 'network', 'Could not reach the server to export the report.');
  }
  if (!response.ok) {
    throw new ApiError(response.status, 'export_failed', 'The report could not be exported.');
  }
  return response.text();
}
