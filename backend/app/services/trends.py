"""Trend discovery: theme identification and evidence-strength scoring.

Everything here is computed from the ACTUAL collected evidence for one run.
No historical claims are made from a single snapshot — outputs are phrased as
"themes observed in the collected results".

SCORING FORMULA (also surfaced in every report's methodology section):

    evidenceStrength = round(
        50 * min(supporting_sources / 4, 1)      # breadth: up to 4+ sources
      + 30 * distinct_domains / total_domains     # diversity across publishers
      + 20 * extracted_ratio                     # full-page text vs snippet-only
    )

- supporting_sources: number of collected sources mentioning the theme.
- distinct_domains / total_domains: ratio of distinct domains among supporters.
- extracted_ratio: share of supporting sources whose full page text was retrieved.

It is a heuristic display aid (0-100), NOT a scientific probability. Bands:
strong >= 70, moderate >= 50, emerging >= 30, tentative < 30.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from ..schemas import EvidenceCoverage, Finding, ThemeCard

FORMULA_TEXT = (
    "evidenceStrength = round(50 * min(supporting_sources/4, 1) "
    "+ 30 * distinct_domains/total_domains + 20 * extracted_ratio); "
    "bands: strong>=70, moderate>=50, emerging>=30, tentative<30. "
    "Heuristic display aid, not a probability."
)

# --------------------------------------------------------------------------
# Term extraction
# --------------------------------------------------------------------------

_STOPWORDS = frozenset(
    """
a an the and or but if then than that this these those of in on at to for from by with
as is are was were be been being it its it's into over under about after before between
during through per vs via not no yes do does did done can could should would will shall
may might must have has had you your we our they their he she his her them i me my
more most less least very too also just only same other another each any all some none
one two three four five six seven eight nine ten first second third new latest recent
best top big large small high low many much such when where why how what which who whom
why's what's how's where's there here out up down off again further once own so because
while above below both few s t don now year years day days week month
us uk india america european
""".split()
)

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.#]{1,}")


def _tokenize(text: str) -> list[str]:
    tokens = []
    for raw in _WORD_RE.findall(text.lower()):
        if raw in _STOPWORDS or len(raw) < 3:
            continue
        tokens.append(raw)
    return tokens


def _singular(word: str) -> str:
    """Very light normalization to merge plural/singular forms."""
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("sses") or word.endswith("shes") or word.endswith("ches"):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]
    return word


# --------------------------------------------------------------------------
# Theme scoring
# --------------------------------------------------------------------------

def compute_strength(
    supporting_sources: int,
    distinct_domains: int,
    total_domains: int,
    extracted_ratio: float,
) -> int:
    """See module docstring for the formula."""
    if supporting_sources <= 0:
        return 0
    breadth = 50 * min(supporting_sources / 4, 1)
    diversity = 30 * (distinct_domains / total_domains) if total_domains else 0
    depth = 20 * max(0.0, min(extracted_ratio, 1.0))
    return int(round(breadth + diversity + depth))


def band_for(score: int) -> str:
    if score >= 70:
        return "strong"
    if score >= 50:
        return "moderate"
    if score >= 30:
        return "emerging"
    return "tentative"


@dataclass
class SourceDoc:
    """A source document as seen by trend analysis."""

    source_id: str
    domain: str
    title: str
    content: str
    extracted: bool
    url: str = ""


def identify_themes(sources: list[SourceDoc], *, max_themes: int = 8) -> list[ThemeCard]:
    """Find recurring multi-word terms and salient single terms across sources.

    A theme must appear in >= 2 sources OR be the top unigram with >= 2 mentions
    in one source — single-source "trends" are explicitly down-weighted.
    """
    if not sources:
        return []

    total_domains = len({s.domain for s in sources}) or 1

    # Document frequency per source for unigrams and bigrams.
    unigram_df: Counter[str] = Counter()
    bigram_df: Counter[str] = Counter()
    unigram_tf: Counter[str] = Counter()
    bigram_tf: Counter[str] = Counter()
    label_map: dict[str, str] = {}

    for doc in sources:
        tokens = _tokenize(f"{doc.title} {doc.content}")
        if not tokens:
            continue
        stems = [_singular(t) for t in tokens]
        seen_uni: set[str] = set()
        seen_bi: set[str] = set()
        for stem in stems:
            unigram_tf[stem] += 1
            if stem not in seen_uni:
                seen_uni.add(stem)
                unigram_df[stem] += 1
            if stem not in label_map:
                label_map[stem] = stem
        for i in range(len(stems) - 1):
            bg = f"{stems[i]} {stems[i + 1]}"
            bigram_tf[bg] += 1
            if bg not in seen_bi:
                seen_bi.add(bg)
                bigram_df[bg] += 1
            if bg not in label_map:
                label_map[bg] = f"{tokens[i]} {tokens[i + 1]}"

    # Bigrams that recur across sources are the strongest theme signal.
    candidates: list[tuple[str, int, int]] = []  # (phrase, df, tf)
    for phrase, df in bigram_df.items():
        if df >= 2:
            candidates.append((phrase, df, bigram_tf[phrase]))
    for phrase, df in unigram_df.items():
        if df >= 3:
            candidates.append((phrase, df, unigram_tf[phrase]))

    if not candidates:
        # Fall back: strongest unigram by frequency (explicitly single-source-limited).
        for phrase, tf in unigram_tf.most_common(3):
            candidates.append((phrase, unigram_df[phrase], tf))

    candidates.sort(key=lambda c: (c[1], c[2]), reverse=True)

    themes: list[ThemeCard] = []
    used_names: set[str] = set()
    for phrase, _df, _tf in candidates:
        if len(themes) >= max_themes:
            break
        name = label_map.get(phrase, phrase).strip()
        if not name or name in used_names:
            continue

        # Which sources mention this phrase?
        supporting: list[SourceDoc] = []
        for doc in sources:
            doc_terms = {_singular(t) for t in _tokenize(f"{doc.title} {doc.content}")}
            phrase_parts = phrase.split()
            if len(phrase_parts) == 1:
                if phrase_parts[0] in doc_terms:
                    supporting.append(doc)
            else:
                # Re-check bigram presence in original token stream.
                tokens = [_singular(t) for t in _tokenize(f"{doc.title} {doc.content}")]
                if any(
                    tokens[i] == phrase_parts[0] and tokens[i + 1] == phrase_parts[1]
                    for i in range(len(tokens) - 1)
                ):
                    supporting.append(doc)

        if not supporting:
            continue

        # Avoid near-duplicate themes (subset phrases of already-chosen themes).
        if any(phrase in existing.lower() or existing.lower() in phrase for existing in used_names):
            continue

        distinct_domains = len({d.domain for d in supporting})
        extracted_ratio = (
            sum(1 for d in supporting if d.extracted) / len(supporting) if supporting else 0
        )
        strength = compute_strength(len(supporting), distinct_domains, total_domains, extracted_ratio)
        confidence = band_for(strength)

        used_names.add(name)
        themes.append(
            ThemeCard(
                id=f"T{len(themes) + 1}",
                name=name.title() if name.islower() else name,
                description=(
                    f"Observed in {len(supporting)} of {len(sources)} collected sources "
                    f"across {distinct_domains} domain{'s' if distinct_domains != 1 else ''}."
                ),
                sourceIds=[d.source_id for d in supporting],
                mentionCount=len(supporting),
                evidenceStrength=strength,
                confidence=confidence,  # type: ignore[arg-type]
                limitations=(
                    "Snapshot of a single search — not a measurement of global trend volume "
                    "or change over time."
                    if len(supporting) < 3
                    else None
                ),
            )
        )

    return themes


# --------------------------------------------------------------------------
# Coverage & generated sections
# --------------------------------------------------------------------------

def compute_coverage(
    key_findings: list[Finding],
    conflicting: int,
) -> EvidenceCoverage:
    """Classify findings by grounding: supported / conflicting / insufficient."""
    supported = sum(1 for f in key_findings if f.evidenceClass == "fact" and f.sourceIds)
    unsupported = sum(1 for f in key_findings if not f.sourceIds)
    return EvidenceCoverage(
        supported=supported,
        conflicting=conflicting,
        insufficient=unsupported,
    )


def build_evidence_package_texts(
    sources: list[SourceDoc],
    theme_count: int,
) -> str:
    """Small helper used for basic-mode summaries (deterministic, labeled)."""
    joined = " ".join(s.content for s in sources)
    return joined[:2000] + (f"… (+{theme_count} themes)" if theme_count else "")


def extract_frequent_terms(sources: list[SourceDoc], limit: int = 12) -> list[tuple[str, int]]:
    counter: Counter[str] = Counter()
    for doc in sources:
        counter.update(_singular(t) for t in _tokenize(f"{doc.title} {doc.content}"))
    return counter.most_common(limit)


def round_to_pow2(n: int) -> int:  # pragma: no cover - tiny utility
    return 1 << int(math.log2(max(1, n)))
