"""End-to-end test of the orchestrator with a fake LLM (no network, no cost)."""

from pathlib import Path

from jobfit.orchestrator import Orchestrator
from jobfit.render import write_outputs
from jobfit.schemas import (
    Experience,
    JobRequirements,
    MatchAssessment,
    Requirement,
    RequirementMatch,
    ResumeProfile,
    ReviewIssue,
    ReviewResult,
    TailoredResume,
)

EXAMPLES = Path(__file__).parent.parent / "examples"
RESUME = (EXAMPLES / "sample_resume.md").read_text(encoding="utf-8")
JOB = (EXAMPLES / "sample_job.txt").read_text(encoding="utf-8")


class FakeLLM:
    """Returns canned objects per schema, in order, and records every call."""

    def __init__(self, responses: dict):
        self.responses = {k: list(v) for k, v in responses.items()}
        self.calls = []

    def structured(self, *, system, content, schema, effort="medium", max_tokens=16000):
        self.calls.append((schema.__name__, effort, content))
        return self.responses[schema].pop(0)


JOB_REQS = JobRequirements(
    title="Software Engineer Intern, ML Platform",
    company="Northwind Robotics",
    seniority="intern",
    summary="Build ML infrastructure.",
    requirements=[
        Requirement(id="R1", text="Strong Python", category="skill", importance="must_have", keywords=["Python"]),
        Requirement(id="R2", text="Kubernetes", category="skill", importance="nice_to_have", keywords=["Kubernetes"]),
    ],
    responsibilities=["Build services"],
    ats_keywords=["Python", "Flask", "Kubernetes", "Airflow"],
)
PROFILE = ResumeProfile(
    name="Alex Rivera", contact_line="alex.rivera@example.com", summary="", skills=["Python"],
    experiences=[Experience(id="E1", title="SWE Intern", organization="Brightline", dates="2025", bullets=[])],
    projects=[], education=[], certifications=[],
)
MATCH = MatchAssessment(
    assessments=[
        RequirementMatch(requirement_id="R1", verdict="strong",
                         evidence=["Built REST API endpoints in Flask"], reasoning="ok"),
        RequirementMatch(requirement_id="R2", verdict="missing", evidence=[], reasoning="none"),
    ],
    strengths=["Python backend work"], gaps=["No Kubernetes"], tailoring_strategy="Lead with the API work.",
)
BAD_DRAFT = TailoredResume(markdown="# Alex Rivera\nLed Kubernetes migration, cut costs 35%", changes=[])
GOOD_DRAFT = TailoredResume(markdown="# Alex Rivera\nBuilt REST API endpoints in Flask", changes=[])
BLOCKER = ReviewResult(approved=True, issues=[  # approved=True on purpose: the code must recompute it
    ReviewIssue(severity="blocker", quote="Led Kubernetes migration", problem="not in resume", fix="remove"),
])
CLEAN = ReviewResult(approved=True, issues=[])


def make_llm():
    return FakeLLM({
        JobRequirements: [JOB_REQS],
        ResumeProfile: [PROFILE],
        MatchAssessment: [MATCH],
        TailoredResume: [BAD_DRAFT, GOOD_DRAFT],
        ReviewResult: [BLOCKER, CLEAN],
    })


def test_full_pipeline_revises_until_reviewer_is_satisfied(tmp_path):
    llm = make_llm()
    events = []
    result = Orchestrator(llm, max_revisions=2, on_event=lambda *e: events.append(e)).run(JOB, RESUME)

    order = [name for name, _, _ in llm.calls]
    assert sorted(order[:2]) == ["JobRequirements", "ResumeProfile"]  # parallel stage
    assert order[2:] == ["MatchAssessment", "TailoredResume", "ReviewResult", "TailoredResume", "ReviewResult"]

    assert result.reviews[0].approved is False  # recomputed from the blocker
    assert result.approved
    assert result.tailored == GOOD_DRAFT
    assert result.new_numbers == []

    # Must-have strong (3/3 weight) + nice-to-have missing (0/1) = 75% requirements;
    # keywords: Python + Flask found, Kubernetes + Airflow not = 50%.
    assert result.fit.requirement_score == 0.75
    assert result.fit.keyword_score == 0.5
    assert result.fit.score == round(100 * (0.85 * 0.75 + 0.15 * 0.5))

    out = write_outputs(result, tmp_path, "examples/sample_job.txt", "test usage")
    report = (out / "fit_report.md").read_text(encoding="utf-8")
    assert (out / "tailored_resume.md").read_text(encoding="utf-8") == GOOD_DRAFT.markdown
    assert "Fit score" in report and "approved by the Reviewer" in report
    assert (out / "run.json").exists()


def test_revision_loop_stops_at_max_revisions_and_guards_still_flag():
    llm = make_llm()
    llm.responses[TailoredResume] = [BAD_DRAFT, BAD_DRAFT]  # writer never fixes it
    llm.responses[ReviewResult] = [BLOCKER, BLOCKER]
    result = Orchestrator(llm, max_revisions=1).run(JOB, RESUME)
    assert len(result.reviews) == 2  # first review + one revision, then stop
    assert not result.approved
    assert result.new_numbers == ["35%"]  # deterministic guard catches the invented metric
    assert result.new_keywords == ["Kubernetes"]


def test_score_only_skips_writer_and_reviewer():
    llm = make_llm()
    result = Orchestrator(llm).run(JOB, RESUME, tailor=False)
    assert result.tailored is None
    assert [c[0] for c in llm.calls if c[0] in ("TailoredResume", "ReviewResult")] == []


def test_agents_use_expected_effort_levels_and_tag_untrusted_input():
    llm = make_llm()
    Orchestrator(llm).run(JOB, RESUME)
    effort = {name: e for name, e, _ in llm.calls}
    assert effort["JobRequirements"] == "low"
    assert effort["TailoredResume"] == "high"
    job_call = next(c for n, _, c in llm.calls if n == "JobRequirements")
    assert "<job_posting>" in job_call
