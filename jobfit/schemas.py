"""Data contracts passed between agents.

Every agent returns one of these Pydantic models. The Claude API's structured
outputs feature constrains the model's reply to the model's JSON schema, so the
next agent always receives well-formed, typed data instead of free text.
"""

from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Job Analyst output
# ---------------------------------------------------------------------------

Importance = Literal["must_have", "nice_to_have"]
Category = Literal["skill", "experience", "education", "certification", "soft_skill", "other"]


class Requirement(BaseModel):
    id: str = Field(description="Short stable id such as R1, R2, ...")
    text: str = Field(description="The requirement, rewritten as one clear sentence")
    category: Category
    importance: Importance = Field(
        description="must_have if the posting says required/must/minimum, else nice_to_have"
    )
    keywords: list[str] = Field(description="1-4 concrete terms a recruiter would search for")


class JobRequirements(BaseModel):
    title: str
    company: str = Field(description="Company name, or 'Unknown' if not stated")
    seniority: Literal["intern", "entry", "mid", "senior", "staff_plus", "unknown"]
    summary: str = Field(description="Two sentences on what the role is about")
    requirements: list[Requirement]
    responsibilities: list[str]
    ats_keywords: list[str] = Field(
        description="10-25 exact terms (tools, languages, methods) an ATS would match on"
    )


# ---------------------------------------------------------------------------
# Resume Parser output
# ---------------------------------------------------------------------------


class Experience(BaseModel):
    id: str = Field(description="Short stable id such as E1, E2, ...")
    title: str
    organization: str
    dates: str
    bullets: list[str] = Field(description="Bullets copied verbatim from the resume")


class Project(BaseModel):
    id: str = Field(description="Short stable id such as P1, P2, ...")
    name: str
    tech: list[str]
    bullets: list[str] = Field(description="Bullets copied verbatim from the resume")


class Education(BaseModel):
    institution: str
    degree: str
    dates: str
    details: list[str]


class ResumeProfile(BaseModel):
    name: str
    contact_line: str = Field(description="Email, phone, links, location exactly as written")
    summary: str = Field(description="The resume's own summary, or empty string if none")
    skills: list[str]
    experiences: list[Experience]
    projects: list[Project]
    education: list[Education]
    certifications: list[str]


# ---------------------------------------------------------------------------
# Matcher output
# ---------------------------------------------------------------------------

Verdict = Literal["strong", "partial", "missing"]


class RequirementMatch(BaseModel):
    requirement_id: str
    verdict: Verdict
    evidence: list[str] = Field(
        description="Short exact quotes copied from the resume that support the verdict; "
        "empty when the verdict is missing"
    )
    reasoning: str = Field(description="One sentence explaining the verdict")


class MatchAssessment(BaseModel):
    assessments: list[RequirementMatch]
    strengths: list[str] = Field(description="Top 3 reasons this candidate fits")
    gaps: list[str] = Field(description="Top 3 gaps, most important first")
    tailoring_strategy: str = Field(
        description="2-3 sentences on what the tailored resume should emphasize"
    )


# ---------------------------------------------------------------------------
# Writer / Reviewer output
# ---------------------------------------------------------------------------


class Change(BaseModel):
    section: str
    what: str = Field(description="What was changed")
    why: str = Field(description="Which job requirement this serves")


class TailoredResume(BaseModel):
    markdown: str = Field(description="The full tailored resume in Markdown")
    changes: list[Change]


class ReviewIssue(BaseModel):
    severity: Literal["blocker", "minor"] = Field(
        description="blocker = fabricated or unsupported claim, or broken structure; "
        "minor = wording or emphasis suggestion"
    )
    quote: str = Field(description="The exact text in the draft that has the problem")
    problem: str
    fix: str


class ReviewResult(BaseModel):
    approved: bool = Field(description="True only if there are no blocker issues")
    issues: list[ReviewIssue]
