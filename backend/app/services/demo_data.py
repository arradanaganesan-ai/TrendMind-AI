"""Clearly labeled demo-mode results.

DEMO DATA IS NEVER PRESENTED AS LIVE INFORMATION:
- All URLs use the reserved `example.com` / `example.org` domains.
- Every demo source title is prefixed "[DEMO]".
- The API marks the run with mode="demo" and the UI shows a Demo badge.
- Analysis runs over this data with the same pipeline as live data, so the UI
  can be tested end-to-end without consuming search credits.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..schemas import SearchResult

_DEMO_TEMPLATES = [
    {
        "title": "[DEMO] Overview and background of {q}",
        "url": "https://example.com/demo/overview",
        "snippet": (
            "This demo entry provides background context about {q}. Industry observers describe "
            "{q} as an active area of development, with adoption varying by sector and region. "
            "Key stakeholders include established vendors, startups, and research groups."
        ),
        "domain": "example.com",
        "date": None,
        "source": "Demo Encyclopedia",
    },
    {
        "title": "[DEMO] Adoption patterns and drivers for {q}",
        "url": "https://example.com/demo/adoption",
        "snippet": (
            "Survey-style demo content about {q} suggests adoption is driven by cost reduction, "
            "regulatory pressure, and competitive demand. Barriers reported include skills "
            "shortages, integration cost, and uncertain return on investment for {q}."
        ),
        "domain": "example.com",
        "date": None,
        "source": "Demo Research Group",
    },
    {
        "title": "[DEMO] Technical approaches compared in {q}",
        "url": "https://example.org/demo/technical-comparison",
        "snippet": (
            "A demo technical comparison of approaches to {q}. Source A emphasizes open standards "
            "and interoperability, while Source B argues proprietary tooling delivers faster time "
            "to value. The claims conflict and would require verification in live research."
        ),
        "domain": "example.org",
        "date": None,
        "source": "Demo Tech Journal",
    },
    {
        "title": "[DEMO] Market participants and funding context for {q}",
        "url": "https://example.org/demo/market",
        "snippet": (
            "Demo market commentary on {q}: participants range from large incumbents to early-stage "
            "startups. Funding activity is described as selective, with investors prioritizing "
            "clear revenue paths. No numeric figures are provided in demo data."
        ),
        "domain": "example.org",
        "date": None,
        "source": "Demo Business Wire",
    },
    {
        "title": "[DEMO] Risks, limitations, and open questions in {q}",
        "url": "https://example.net/demo/risks",
        "snippet": (
            "This demo source lists risks associated with {q}: data quality, governance gaps, "
            "vendor lock-in, and rapidly changing standards. It also notes missing information — "
            "long-term outcomes for {q} are not yet documented."
        ),
        "domain": "example.net",
        "date": None,
        "source": "Demo Risk Review",
    },
    {
        "title": "[DEMO] Practical guidance for teams evaluating {q}",
        "url": "https://example.net/demo/guidance",
        "snippet": (
            "Demo practitioner guidance on {q}: start with a narrow use case, measure outcomes, "
            "and review security requirements early. The article recommends follow-up questions "
            "rather than relying on a single source when evaluating {q}."
        ),
        "domain": "example.net",
        "date": None,
        "source": "Demo Practice Hub",
    },
    {
        "title": "[DEMO] Regulatory and policy landscape around {q}",
        "url": "https://example.com/demo/policy",
        "snippet": (
            "A demo overview of policy considerations for {q}. Emerging guidance focuses on "
            "transparency, accountability, and reporting requirements. Compliance timelines differ "
            "by jurisdiction, which affects planning for {q}."
        ),
        "domain": "example.com",
        "date": None,
        "source": "Demo Policy Desk",
    },
    {
        "title": "[DEMO] Skills and workforce considerations for {q}",
        "url": "https://example.org/demo/workforce",
        "snippet": (
            "Demo workforce analysis for {q}: demand for related skills is rising, and teams report "
            "difficulty hiring experienced practitioners. Training and tooling maturity are "
            "recurring themes mentioned in connection with {q}."
        ),
        "domain": "example.org",
        "date": None,
        "source": "Demo Careers Report",
    },
]


def demo_search(query: str, num_results: int = 10) -> list[SearchResult]:
    """Build clearly-labeled demo results for an arbitrary query."""
    from urllib.parse import urlparse

    count = max(1, min(num_results, len(_DEMO_TEMPLATES)))
    q = query.strip() or "the topic"
    results: list[SearchResult] = []
    for i, tpl in enumerate(_DEMO_TEMPLATES[:count], start=1):
        url = tpl["url"]
        domain = urlparse(url).hostname or tpl["domain"]
        results.append(
            SearchResult(
                position=i,
                title=tpl["title"].format(q=q),
                url=url,
                snippet=tpl["snippet"].format(q=q),
                domain=domain,
                publishedDate=tpl["date"],
                source=tpl["source"],
            )
        )
    return results


def demo_searched_at() -> str:
    return datetime.now(timezone.utc).isoformat()
