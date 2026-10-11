"""Deterministic scoring and fact-checking - plain Python, no LLM.

Why not just ask Claude for a 0-100 score? Because a number an LLM invents is
hard to explain and drifts between runs. Instead, Claude only judges each
requirement (strong / partial / missing, with quoted evidence) and this module
turns those judgments into a score with a fixed, transparent formula.

It also double-checks the LLM's work:
  * evidence quotes must actually appear in the resume, otherwise the verdict
    is downgraded (catches hallucinated evidence);
  * numbers in the tailored resume must exist in the original resume
    (catches invented metrics like "improved speed by 40%").
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .schemas import JobRequirements, MatchAssessment, RequirementMatch

IMPORTANCE_WEIGHT = {"must_have": 3.0, "nice_to_have": 1.0}
VERDICT_VALUE = {"strong": 1.0, "partial": 0.5, "missing": 0.0}
DOWNGRADE = {"strong": "partial", "partial": "missing", "missing": "missing"}

REQUIREMENT_SHARE = 0.85  # final score = 85% requirement coverage
KEYWORD_SHARE = 0.15  # + 15% ATS keyword coverage

BANDS = [(75, "Strong fit"), (55, "Good fit"), (35, "Stretch")]


@dataclass
class ScoredRequirement:
    id: str
    text: str
    importance: str
    verdict: str
    original_verdict: str
    evidence: list[str]
    unverified_evidence: list[str]
    reasoning: str


@dataclass
class FitScore:
    score: int
    band: str
    requirement_score: float
    keyword_score: float
    matched_keywords: list[str]
    missing_keywords: list[str]
    missing_must_haves: list[str]
    requirements: list[ScoredRequirement] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------


def normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[*_`#>|]", " ", text)  # strip Markdown symbols
    text = re.sub(r"[‐-―]", "-", text)  # unify dashes
    return re.sub(r"\s+", " ", text).strip()


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9+#.]+", normalize(text))


def evidence_is_grounded(quote: str, resume_text: str, min_overlap: float = 0.8) -> bool:
    """True if the quote is in the resume, allowing for small rewording."""
    q, r = normalize(quote), normalize(resume_text)
    if not q:
        return False
    if q in r:
        return True
    quote_words = _words(quote)
    if not quote_words:
        return False
    resume_words = set(_words(resume_text))
    hits = sum(1 for w in quote_words if w in resume_words)
    return hits / len(quote_words) >= min_overlap


def keyword_in_text(keyword: str, text: str) -> bool:
    """Whole-word, case-insensitive match that also works for 'C++', 'C#', 'Node.js'."""
    # '+' and '#' count as part of a word so "C" doesn't match inside "C++" or "C#".
    pattern = r"(?<![a-z0-9+#])" + re.escape(normalize(keyword)) + r"(?![a-z0-9+#])"
    return re.search(pattern, normalize(text)) is not None


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def score_fit(job: JobRequirements, match: MatchAssessment, resume_text: str) -> FitScore:
    by_id: dict[str, RequirementMatch] = {m.requirement_id: m for m in match.assessments}
    warnings: list[str] = []
    scored: list[ScoredRequirement] = []
    earned = total = 0.0

    for req in job.requirements:
        m = by_id.get(req.id)
        if m is None:
            warnings.append(f"Matcher skipped {req.id}; counted as missing.")
            m = RequirementMatch(requirement_id=req.id, verdict="missing", evidence=[], reasoning="Not assessed.")

        grounded = [e for e in m.evidence if evidence_is_grounded(e, resume_text)]
        unverified = [e for e in m.evidence if e not in grounded]
        verdict = m.verdict
        if verdict != "missing" and not grounded:
            verdict = DOWNGRADE[verdict]
            warnings.append(
                f"{req.id}: none of the quoted evidence was found in the resume; "
                f"downgraded {m.verdict} -> {verdict}."
            )

        weight = IMPORTANCE_WEIGHT[req.importance]
        earned += weight * VERDICT_VALUE[verdict]
        total += weight
        scored.append(
            ScoredRequirement(
                id=req.id,
                text=req.text,
                importance=req.importance,
                verdict=verdict,
                original_verdict=m.verdict,
                evidence=grounded,
                unverified_evidence=unverified,
                reasoning=m.reasoning,
            )
        )

    requirement_score = earned / total if total else 0.0

    keywords = list(dict.fromkeys(k.strip() for k in job.ats_keywords if k.strip()))
    matched = [k for k in keywords if keyword_in_text(k, resume_text)]
    missing = [k for k in keywords if k not in matched]
    keyword_score = len(matched) / len(keywords) if keywords else 0.0

    score = round(100 * (REQUIREMENT_SHARE * requirement_score + KEYWORD_SHARE * keyword_score))
    band = next((label for cutoff, label in BANDS if score >= cutoff), "Weak fit")

    return FitScore(
        score=score,
        band=band,
        requirement_score=requirement_score,
        keyword_score=keyword_score,
        matched_keywords=matched,
        missing_keywords=missing,
        missing_must_haves=[r.text for r in scored if r.importance == "must_have" and r.verdict == "missing"],
        requirements=scored,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Guard on the final tailored resume
# ---------------------------------------------------------------------------

NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?\s*(?:%|\+|x|k|m)?", re.IGNORECASE)


def _numbers(text: str) -> set[str]:
    return {re.sub(r"[\s,]", "", n).lower() for n in NUMBER_RE.findall(text)}


def find_new_numbers(original: str, tailored: str) -> list[str]:
    """Numbers (metrics, years, counts) in the tailored resume that the original never had."""
    return sorted(_numbers(tailored) - _numbers(original))


def find_new_keywords(original: str, tailored: str, keywords: list[str]) -> list[str]:
    """Job keywords that appear in the tailored resume but not in the original one."""
    return [k for k in keywords if keyword_in_text(k, tailored) and not keyword_in_text(k, original)]
