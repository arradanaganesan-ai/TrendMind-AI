"""Pydantic request/response schemas — the API contract shared with the frontend."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

EvidenceClass = Literal["fact", "interpretation", "hypothesis"]
SearchMode = Literal["live", "demo"]
AiMode = Literal["llm", "basic"]
ResearchStatus = Literal["pending", "completed", "failed"]
ContentBasis = Literal["extracted", "snippets", "mixed", "demo"]
ExtractionStatus = Literal["extracted", "snippet_only", "blocked", "failed", "skipped"]
Confidence = Literal["strong", "moderate", "emerging", "tentative"]


# --------------------------------------------------------------------------
# Requests
# --------------------------------------------------------------------------

ALLOWED_CATEGORIES = {"general", "news", "technology", "science", "business"}
ALLOWED_REGIONS = {"us", "in", "gb", "ca", "au", "de", "fr", "jp", "br", "sg"}
ALLOWED_LANGUAGES = {"en", "es", "fr", "de", "hi", "pt", "ja"}
ALLOWED_TIME_RANGES = {"any", "day", "week", "month", "year"}


class ResearchFilters(BaseModel):
    """Optional search filters. Unknown values are rejected (422)."""

    category: Literal["general", "news", "technology", "science", "business"] = "general"
    region: str = "us"
    language: str = "en"
    timeRange: Literal["any", "day", "week", "month", "year"] = "any"
    numResults: int = Field(default=10, ge=1, le=50)

    @field_validator("region")
    @classmethod
    def _region_supported(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in ALLOWED_REGIONS:
            raise ValueError(f"Unsupported region '{v}'. Allowed: {', '.join(sorted(ALLOWED_REGIONS))}")
        return v

    @field_validator("language")
    @classmethod
    def _language_supported(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in ALLOWED_LANGUAGES:
            raise ValueError(f"Unsupported language '{v}'. Allowed: {', '.join(sorted(ALLOWED_LANGUAGES))}")
        return v


class ResearchRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=300)
    filters: ResearchFilters | None = None

    @field_validator("query")
    @classmethod
    def _clean_query(cls, v: str) -> str:
        cleaned = " ".join(v.split())
        if len(cleaned) < 2:
            raise ValueError("Query must be at least 2 characters.")
        if len(cleaned) > 300:
            raise ValueError("Query is limited to 300 characters.")
        return cleaned


class TopicCreate(BaseModel):
    topic: str = Field(..., min_length=1, max_length=200)

    @field_validator("topic")
    @classmethod
    def _clean_topic(cls, v: str) -> str:
        cleaned = " ".join(v.split())
        if not cleaned:
            raise ValueError("Topic cannot be empty.")
        return cleaned


class TrackedTopicCreate(BaseModel):
    """Start tracking an existing research query (one query = one topic)."""

    query: str = Field(..., min_length=2, max_length=300)

    @field_validator("query")
    @classmethod
    def _clean_query(cls, v: str) -> str:
        cleaned = " ".join(v.split())
        if len(cleaned) < 2:
            raise ValueError("Query must be at least 2 characters.")
        if len(cleaned) > 300:
            raise ValueError("Query is limited to 300 characters.")
        return cleaned


# --------------------------------------------------------------------------
# Search results / sources
# --------------------------------------------------------------------------

class SearchResult(BaseModel):
    position: int
    title: str
    url: str
    snippet: str
    domain: str
    publishedDate: str | None = None
    source: str | None = None


class SourceRef(BaseModel):
    id: str
    title: str
    url: str
    domain: str
    snippet: str
    publishedDate: str | None = None
    extracted: bool = False
    extractionStatus: ExtractionStatus = "snippet_only"
    # User-safe, truncated explanation of WHY a page was not retrieved
    # (e.g. robots.txt restriction, timeout). None when not attempted.
    extractionNote: str | None = None


# --------------------------------------------------------------------------
# Report (strict structured schema)
# --------------------------------------------------------------------------

class Finding(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    sourceIds: list[str] = Field(default_factory=list, max_length=12)
    evidenceClass: EvidenceClass = "fact"
    caveat: str | None = Field(default=None, max_length=500)


class ThemeCard(BaseModel):
    id: str
    name: str = Field(..., min_length=1, max_length=120)
    description: str = Field(..., min_length=1, max_length=800)
    sourceIds: list[str] = Field(default_factory=list, max_length=30)
    mentionCount: int = 0
    evidenceStrength: int = Field(default=0, ge=0, le=100)
    confidence: Confidence = "tentative"
    limitations: str | None = Field(default=None, max_length=500)


class ClaimGroup(BaseModel):
    sourceIds: list[str] = Field(default_factory=list, max_length=12)
    claim: str = Field(..., min_length=1, max_length=1200)


class EvidenceComparison(BaseModel):
    aspect: str = Field(..., min_length=1, max_length=200)
    claims: list[ClaimGroup] = Field(default_factory=list, max_length=8)
    note: str | None = Field(default=None, max_length=600)


class ConflictPosition(BaseModel):
    sourceIds: list[str] = Field(default_factory=list, max_length=12)
    position: str = Field(..., min_length=1, max_length=1200)


class ConflictItem(BaseModel):
    topic: str = Field(..., min_length=1, max_length=200)
    positions: list[ConflictPosition] = Field(default_factory=list, min_length=2, max_length=6)
    note: str | None = Field(default=None, max_length=600)


class EvidenceCoverage(BaseModel):
    supported: int = 0
    conflicting: int = 0
    insufficient: int = 0


class ReportMethodology(BaseModel):
    searchMode: SearchMode
    aiMode: AiMode
    contentBasis: ContentBasis
    resultCount: int
    extractedPageCount: int
    snippetOnlyCount: int
    scoringFormula: str
    notes: list[str] = Field(default_factory=list, max_length=20)


class ResearchReport(BaseModel):
    researchQuestion: str
    executiveSummary: str = Field(..., min_length=1, max_length=4000)
    keyFindings: list[Finding] = Field(default_factory=list, max_length=15)
    themes: list[ThemeCard] = Field(default_factory=list, max_length=12)
    evidenceComparison: list[EvidenceComparison] = Field(default_factory=list, max_length=8)
    conflictingClaims: list[ConflictItem] = Field(default_factory=list, max_length=8)
    emergingDevelopments: list[Finding] = Field(default_factory=list, max_length=10)
    opportunities: list[Finding] = Field(default_factory=list, max_length=10)
    risksAndLimitations: list[str] = Field(default_factory=list, max_length=15)
    followUpQuestions: list[str] = Field(default_factory=list, max_length=10)
    sources: list[SourceRef] = Field(default_factory=list, max_length=60)
    coverage: EvidenceCoverage = Field(default_factory=EvidenceCoverage)
    methodology: ReportMethodology
    searchedAt: str
    generatedAt: str


# --------------------------------------------------------------------------
# Records
# --------------------------------------------------------------------------

class ResearchListItem(BaseModel):
    id: str
    query: str
    createdAt: str
    status: ResearchStatus
    mode: SearchMode
    resultCount: int
    aiMode: AiMode
    errorMessage: str | None = None


class ResearchRecord(BaseModel):
    id: str
    query: str
    createdAt: str
    status: ResearchStatus
    mode: SearchMode
    resultCount: int
    aiMode: AiMode
    errorMessage: str | None = None
    filters: ResearchFilters | None = None
    results: list[SearchResult] = Field(default_factory=list)
    report: ResearchReport | None = None


class ResearchListResponse(BaseModel):
    items: list[ResearchListItem]
    total: int


class SavedTopic(BaseModel):
    id: str
    topic: str
    createdAt: str


class TopicListResponse(BaseModel):
    items: list[SavedTopic]


# --------------------------------------------------------------------------
# Health / config
# --------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "trendmind-ai"
    version: str
    time: str


class WorkspaceStats(BaseModel):
    """Real database-backed counters for this instance. No estimates."""

    researchTotal: int = 0
    researchCompleted: int = 0
    researchFailed: int = 0
    reportsTotal: int = 0
    savedTopics: int = 0
    last7DaysResearch: int = 0
    last7DaysCompleted: int = 0


class ActivityPoint(BaseModel):
    """One UTC calendar day of real research activity (zero-filled)."""

    date: str  # YYYY-MM-DD
    count: int
    completed: int


class ActivityResponse(BaseModel):
    days: int
    points: list[ActivityPoint]


class ConfigStatus(BaseModel):
    version: str
    searchMode: SearchMode
    serpapiConfigured: bool
    aiProvider: str
    aiConfigured: bool
    sourceExtractionEnabled: bool
    demoMode: bool
    maxResultsLimit: int
    githubRepoUrl: str | None = None


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Any | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


# --------------------------------------------------------------------------
# Report comparison
# --------------------------------------------------------------------------

class FindingRef(BaseModel):
    """A finding referenced by its position in the originating report."""

    index: int = Field(ge=0)
    text: str
    evidenceClass: EvidenceClass = "fact"
    sourceIds: list[str] = Field(default_factory=list)
    caveat: str | None = None


class FindingPair(BaseModel):
    """Two findings judged to describe the same claim."""

    a: FindingRef
    b: FindingRef
    similarity: float = Field(ge=0.0, le=1.0)
    matchType: Literal["exact", "similar"]
    sharedSourceIds: list[str] = Field(default_factory=list)


class ConflictCandidate(BaseModel):
    """Findings about the same subject with opposing polarity.

    Basic-mode candidates are never presented as confirmed contradictions —
    `insufficientEvidence` stays True until a human (or the AI pass) reviews
    the cited sources.
    """

    a: FindingRef
    b: FindingRef
    similarity: float = Field(ge=0.0, le=1.0)
    status: Literal["possible_conflict", "ai_reviewed_conflict"]
    explanation: str
    insufficientEvidence: bool = True


class ComparedRun(BaseModel):
    """Identity of one side of the comparison."""

    id: str
    query: str
    researchQuestion: str
    createdAt: str
    searchedAt: str
    mode: SearchMode
    aiMode: AiMode
    findingCount: int
    sourceCount: int


class SourceComparison(BaseModel):
    """Overlap between the two reports' source lists (matched by exact URL)."""

    sharedUrls: list[str] = Field(default_factory=list)  # bounded for transport
    sharedCount: int = 0
    onlyACount: int = 0
    onlyBCount: int = 0
    sharedDomains: list[str] = Field(default_factory=list)


class ComparisonMethodology(BaseModel):
    """How the comparison was computed — never claims more than was done."""

    mode: Literal["basic", "ai"]
    explanation: list[str] = Field(default_factory=list)
    aiNote: str | None = None


class ReportComparison(BaseModel):
    runA: ComparedRun
    runB: ComparedRun
    sharedFindings: list[FindingPair] = Field(default_factory=list)
    similarFindings: list[FindingPair] = Field(default_factory=list)
    conflicts: list[ConflictCandidate] = Field(default_factory=list)
    uniqueToA: list[FindingRef] = Field(default_factory=list)
    uniqueToB: list[FindingRef] = Field(default_factory=list)
    sources: SourceComparison
    methodology: ComparisonMethodology
    temporalNote: str | None = None
    noveltyCaveat: str


# ---------------------------------------------------------------------------
# Historical trend tracking (dated snapshots over real research runs)
# ---------------------------------------------------------------------------

class TrackedTopic(BaseModel):
    """A query the user chose to follow across research runs."""

    id: str
    query: str
    createdAt: str
    snapshotCount: int = 0
    firstSnapshotAt: str | None = None
    lastSnapshotAt: str | None = None


class TrackedTopicListResponse(BaseModel):
    items: list[TrackedTopic]


class TrendCandidate(BaseModel):
    """A query with completed runs — offered for tracking (real data only)."""

    query: str
    runCount: int = Field(ge=1)
    firstRunAt: str
    lastRunAt: str


class TrendCandidateListResponse(BaseModel):
    items: list[TrendCandidate]


class SnapshotTheme(BaseModel):
    """One theme as observed in a single dated snapshot."""

    name: str
    mentionCount: int = 0
    evidenceStrength: int = Field(ge=0, le=100)
    confidence: Confidence = "tentative"


class SnapshotRef(BaseModel):
    """Identity + real timestamp of one snapshot."""

    researchId: str
    createdAt: str
    searchedAt: str


class TimelineSnapshot(BaseModel):
    """One dated snapshot: a stored research run and its real report payload."""

    researchId: str
    query: str
    createdAt: str
    searchedAt: str
    mode: SearchMode
    aiMode: AiMode
    resultCount: int
    findingCount: int
    sourceCount: int
    domainCount: int
    findings: list[FindingRef] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)
    themes: list[SnapshotTheme] = Field(default_factory=list)


class SourceCoverageDelta(BaseModel):
    """Source overlap between two consecutive snapshots (matched by exact URL)."""

    sharedCount: int = 0
    addedCount: int = 0
    removedCount: int = 0
    addedUrls: list[str] = Field(default_factory=list)  # bounded for transport
    removedUrls: list[str] = Field(default_factory=list)
    addedDomains: list[str] = Field(default_factory=list)
    removedDomains: list[str] = Field(default_factory=list)


class ThemeScoreChange(BaseModel):
    """Evidence-strength delta for a theme observed in BOTH snapshots.

    Only themes whose (normalized) names match are comparable — anything else
    is reported as not comparable rather than interpolated.
    """

    theme: str
    olderStrength: int = Field(ge=0, le=100)
    newerStrength: int = Field(ge=0, le=100)
    delta: int = Field(ge=-100, le=100)
    olderConfidence: Confidence = "tentative"
    newerConfidence: Confidence = "tentative"


class SnapshotChange(BaseModel):
    """Deterministic deltas between two consecutive dated snapshots."""

    fromSnapshot: SnapshotRef
    toSnapshot: SnapshotRef
    daysApart: float = Field(ge=0.0)
    unchangedCount: int = 0
    newlyObserved: list[FindingRef] = Field(default_factory=list)
    noLongerObserved: list[FindingRef] = Field(default_factory=list)
    absenceCaveat: str
    sourceCoverage: SourceCoverageDelta
    themeScoreChanges: list[ThemeScoreChange] = Field(default_factory=list)
    incomparableThemes: list[str] = Field(default_factory=list)


class TrendMethodology(BaseModel):
    """How the timeline was computed — never claims more than was done."""

    mode: Literal["basic", "ai"]
    explanation: list[str] = Field(default_factory=list)
    aiNote: str | None = None
    aiSummary: str | None = None


class TrendTimeline(BaseModel):
    """Snapshots (oldest-first) + changes between consecutive snapshots."""

    topic: TrackedTopic
    snapshots: list[TimelineSnapshot] = Field(default_factory=list)
    changes: list[SnapshotChange] = Field(default_factory=list)
    methodology: TrendMethodology
    singleSnapshotNote: str | None = None
    dateFrom: str | None = None
    dateTo: str | None = None
