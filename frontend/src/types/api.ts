/**
 * TrendMind AI — typed API contract.
 * Mirrors the backend Pydantic schemas in backend/app/schemas/.
 */

// ---------------------------------------------------------------------------
// Search / research request
// ---------------------------------------------------------------------------

export type SearchMode = 'live' | 'demo';
export type AiMode = 'llm' | 'basic';
export type ResearchStatus = 'pending' | 'completed' | 'failed';
export type ContentBasis = 'extracted' | 'snippets' | 'mixed' | 'demo';

/** Filters are only sent when the backend actually supports them. */
export interface ResearchFilters {
  /** e.g. general | news | science | technology | business */
  category?: string;
  /** SerpApi `gl` country code, e.g. us, in, gb */
  region?: string;
  /** SerpApi `hl` language code, e.g. en, es */
  language?: string;
  /** e.g. any | day | week | month | year */
  timeRange?: string;
  /** Number of search results (bounded server-side). */
  numResults?: number;
}

export interface ResearchRequest {
  query: string;
  filters?: ResearchFilters;
}

// ---------------------------------------------------------------------------
// Search results & sources
// ---------------------------------------------------------------------------

export interface SearchResult {
  position: number;
  title: string;
  url: string;
  snippet: string;
  domain: string;
  publishedDate?: string | null;
  source?: string | null;
}

/** A collected source, used for citation. `id` is the citation key (e.g. "S1"). */
export interface SourceRef {
  id: string;
  title: string;
  url: string;
  domain: string;
  snippet: string;
  publishedDate?: string | null;
  /** true when the full page text was retrieved; false when snippet-only. */
  extracted: boolean;
  extractionStatus: 'extracted' | 'snippet_only' | 'blocked' | 'failed' | 'skipped';
}

// ---------------------------------------------------------------------------
// Analysis output (strict structured schema)
// ---------------------------------------------------------------------------

/** How a claim is grounded in evidence. */
export type EvidenceClass = 'fact' | 'interpretation' | 'hypothesis';

export interface Finding {
  text: string;
  /** Citation keys that must exist in `sources`. Validated server-side. */
  sourceIds: string[];
  evidenceClass: EvidenceClass;
  /** Short note when evidence is thin or the claim is contested. */
  caveat?: string;
}

export interface ThemeCard {
  id: string;
  name: string;
  description: string;
  /** Sources (from collected evidence) that mention this theme. */
  sourceIds: string[];
  /** Number of collected sources mentioning the theme. */
  mentionCount: number;
  /** 0–100, computed with the documented formula — not a probability. */
  evidenceStrength: number;
  /** Qualitative band derived from evidenceStrength. */
  confidence: 'strong' | 'moderate' | 'emerging' | 'tentative';
  limitations?: string;
}

export interface EvidenceComparison {
  aspect: string;
  claims: { sourceIds: string[]; claim: string }[];
  note?: string;
}

export interface ConflictItem {
  topic: string;
  positions: { sourceIds: string[]; position: string }[];
  note?: string;
}

export interface EvidenceCoverage {
  supported: number;
  conflicting: number;
  insufficient: number;
}

export interface ReportMethodology {
  searchMode: SearchMode;
  aiMode: AiMode;
  contentBasis: ContentBasis;
  resultCount: number;
  extractedPageCount: number;
  snippetOnlyCount: number;
  scoringFormula: string;
  notes: string[];
}

export interface ResearchReport {
  researchQuestion: string;
  executiveSummary: string;
  keyFindings: Finding[];
  themes: ThemeCard[];
  evidenceComparison: EvidenceComparison[];
  conflictingClaims: ConflictItem[];
  emergingDevelopments: Finding[];
  opportunities: Finding[];
  risksAndLimitations: string[];
  followUpQuestions: string[];
  sources: SourceRef[];
  coverage: EvidenceCoverage;
  methodology: ReportMethodology;
  /** ISO timestamp of when the search was performed. */
  searchedAt: string;
  /** ISO timestamp of when the report was generated. */
  generatedAt: string;
}

// ---------------------------------------------------------------------------
// Records
// ---------------------------------------------------------------------------

export interface ResearchListItem {
  id: string;
  query: string;
  createdAt: string;
  status: ResearchStatus;
  mode: SearchMode;
  resultCount: number;
  aiMode: AiMode;
  errorMessage?: string | null;
}

export interface ResearchRecord extends ResearchListItem {
  filters?: ResearchFilters | null;
  results: SearchResult[];
  report?: ResearchReport | null;
}

export interface SavedTopic {
  id: string;
  topic: string;
  createdAt: string;
}

// ---------------------------------------------------------------------------
// Config / health
// ---------------------------------------------------------------------------

export interface ConfigStatus {
  version: string;
  searchMode: SearchMode;
  serpapiConfigured: boolean;
  aiProvider: string;
  aiConfigured: boolean;
  sourceExtractionEnabled: boolean;
  demoMode: boolean;
  maxResultsLimit: number;
  githubRepoUrl: string | null;
}

export interface HealthResponse {
  status: 'ok';
  service: string;
  version: string;
  time: string;
}

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details?: unknown;
  };
}
