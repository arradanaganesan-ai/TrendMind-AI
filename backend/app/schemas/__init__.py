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
