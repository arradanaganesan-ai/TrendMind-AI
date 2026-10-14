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
  /** User-safe explanation of why the page was not retrieved (blocked/failed). */
  extractionNote?: string | null;
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

/**
 * Honest pipeline progress stages, emitted by `POST /api/research/stream`
 * at real step boundaries. "extracting" is only emitted when page extraction
 * actually runs (live mode with extraction enabled).
 */
export type ResearchStage = 'searching' | 'extracting' | 'analyzing' | 'validating';

/**
 * One UTC calendar day of real research activity (server-side COUNT over
 * existing rows; days without runs are explicit zeros, never interpolated).
 */
export interface ActivityPoint {
  date: string; // YYYY-MM-DD
  count: number;
  completed: number;
}

export interface ActivityResponse {
  days: number;
  points: ActivityPoint[];
}

/**
 * Workspace counters. Every value is a real database COUNT computed on the
 * backend for this instance — never estimated or fabricated.
 */
export interface WorkspaceStats {
  researchTotal: number;
  researchCompleted: number;
  researchFailed: number;
  /** Completed runs that have a stored report available to open/export. */
  reportsTotal: number;
  savedTopics: number;
  last7DaysResearch: number;
  last7DaysCompleted: number;
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

// ---------------------------------------------------------------------------
// Report comparison
// ---------------------------------------------------------------------------

/** A finding referenced by its position in the originating report. */
export interface ComparedFindingRef {
  index: number;
  text: string;
  evidenceClass: EvidenceClass;
  sourceIds: string[];
  caveat: string | null;
}

/** Two findings judged to describe the same claim. */
export interface ComparedFindingPair {
  a: ComparedFindingRef;
  b: ComparedFindingRef;
  similarity: number;
  matchType: 'exact' | 'similar';
  sharedSourceIds: string[];
}

export interface ComparedConflict {
  a: ComparedFindingRef;
  b: ComparedFindingRef;
  similarity: number;
  status: 'possible_conflict' | 'ai_reviewed_conflict';
  explanation: string;
  /** True until a human (or the AI pass) has actually reviewed the sources. */
  insufficientEvidence: boolean;
}

export interface ComparedRun {
  id: string;
  query: string;
  researchQuestion: string;
  createdAt: string;
  searchedAt: string;
  mode: SearchMode;
  aiMode: AiMode;
  findingCount: number;
  sourceCount: number;
}

export interface ComparedSources {
  sharedUrls: string[];
  sharedCount: number;
  onlyACount: number;
  onlyBCount: number;
  sharedDomains: string[];
}

export interface ComparisonMethodology {
  mode: 'basic' | 'ai';
  explanation: string[];
  aiNote: string | null;
}

export interface ReportComparison {
  runA: ComparedRun;
  runB: ComparedRun;
  sharedFindings: ComparedFindingPair[];
  similarFindings: ComparedFindingPair[];
  conflicts: ComparedConflict[];
  uniqueToA: ComparedFindingRef[];
  uniqueToB: ComparedFindingRef[];
  sources: ComparedSources;
  methodology: ComparisonMethodology;
  temporalNote: string | null;
  noveltyCaveat: string;
}

// ---------------------------------------------------------------------------
// Historical trend tracking (dated snapshots over real research runs)
// ---------------------------------------------------------------------------

/** A query the user chose to follow across research runs. */
export interface TrackedTopic {
  id: string;
  query: string;
  createdAt: string;
  /** Real count of stored completed runs with a report for this query. */
  snapshotCount: number;
  firstSnapshotAt: string | null;
  lastSnapshotAt: string | null;
}

/** A query with completed runs — offered for tracking (real data only). */
export interface TrendCandidate {
  query: string;
  runCount: number;
  firstRunAt: string;
  lastRunAt: string;
}

/** One theme as observed in a single dated snapshot. */
export interface SnapshotTheme {
  name: string;
  mentionCount: number;
  /** 0–100, from that run's own evidence — not a probability. */
  evidenceStrength: number;
  confidence: 'strong' | 'moderate' | 'emerging' | 'tentative';
}

/** Identity + real timestamp of one snapshot. */
export interface SnapshotRef {
  researchId: string;
  createdAt: string;
  searchedAt: string;
}

/** One dated snapshot: a stored research run and its real report payload. */
export interface TimelineSnapshot {
  researchId: string;
  query: string;
  createdAt: string;
  searchedAt: string;
  mode: SearchMode;
  aiMode: AiMode;
  resultCount: number;
  findingCount: number;
  sourceCount: number;
  domainCount: number;
  findings: ComparedFindingRef[];
  sources: SourceRef[];
  themes: SnapshotTheme[];
}

/** Source overlap between two consecutive snapshots (matched by exact URL). */
export interface SourceCoverageDelta {
  sharedCount: number;
  addedCount: number;
  removedCount: number;
  /** Bounded lists (backend caps transport size). */
  addedUrls: string[];
  removedUrls: string[];
  addedDomains: string[];
  removedDomains: string[];
}

/** Evidence-strength delta for a theme observed in BOTH snapshots only. */
export interface ThemeScoreChange {
  theme: string;
  olderStrength: number;
  newerStrength: number;
  delta: number;
  olderConfidence: 'strong' | 'moderate' | 'emerging' | 'tentative';
  newerConfidence: 'strong' | 'moderate' | 'emerging' | 'tentative';
}

/** Deterministic deltas between two consecutive dated snapshots. */
export interface SnapshotChange {
  fromSnapshot: SnapshotRef;
  toSnapshot: SnapshotRef;
  daysApart: number;
  unchangedCount: number;
  newlyObserved: ComparedFindingRef[];
  /** Absent from the newer search — never "proven false". */
  noLongerObserved: ComparedFindingRef[];
  absenceCaveat: string;
  sourceCoverage: SourceCoverageDelta;
  themeScoreChanges: ThemeScoreChange[];
  /** Theme names present on only one side — reported as not comparable. */
  incomparableThemes: string[];
}

export interface TrendMethodology {
  mode: 'basic' | 'ai';
  explanation: string[];
  aiNote: string | null;
  aiSummary: string | null;
}

/** Snapshots (oldest-first) + changes between consecutive snapshots. */
export interface TrendTimeline {
  topic: TrackedTopic;
  snapshots: TimelineSnapshot[];
  changes: SnapshotChange[];
  methodology: TrendMethodology;
  /** Set only when exactly one dated snapshot exists. */
  singleSnapshotNote: string | null;
  dateFrom: string | null;
  dateTo: string | null;
}
