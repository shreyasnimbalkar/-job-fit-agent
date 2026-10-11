from jobfit.schemas import JobRequirements, MatchAssessment, Requirement, RequirementMatch
from jobfit.scoring import (
    evidence_is_grounded,
    find_new_keywords,
    find_new_numbers,
    keyword_in_text,
    score_fit,
)

RESUME = """Alex Rivera
Built REST API endpoints in Flask for a dashboard used by 120 analysts
Skills: Python, C++, Node.js, PostgreSQL, Docker"""


def make_job(reqs, keywords=()):
    return JobRequirements(
        title="SWE Intern", company="Acme", seniority="intern", summary="x",
        requirements=reqs, responsibilities=[], ats_keywords=list(keywords),
    )


def req(id, importance="must_have"):
    return Requirement(id=id, text=f"req {id}", category="skill", importance=importance, keywords=[])


def m(id, verdict, evidence=()):
    return RequirementMatch(requirement_id=id, verdict=verdict, evidence=list(evidence), reasoning="r")


def assessment(*matches):
    return MatchAssessment(assessments=list(matches), strengths=[], gaps=[], tailoring_strategy="")


def test_keyword_matching_handles_symbols_and_word_boundaries():
    assert keyword_in_text("C++", RESUME)
    assert keyword_in_text("node.js", RESUME)
    assert keyword_in_text("python", RESUME)
    assert not keyword_in_text("C", "I know C++ only")  # 'C' must not match inside 'C++'
    assert not keyword_in_text("Java", "I know JavaScript")


def test_evidence_grounding_allows_light_rewording_but_rejects_inventions():
    assert evidence_is_grounded("Built REST API endpoints in Flask", RESUME)
    assert evidence_is_grounded("**built** REST API endpoints in flask", RESUME)  # markdown/case
    assert not evidence_is_grounded("Led a team of 8 engineers on Kubernetes", RESUME)


def test_weighted_score_must_haves_count_triple():
    job = make_job([req("R1"), req("R2", "nice_to_have")])
    match = assessment(m("R1", "strong", ["Python"]), m("R2", "missing"))
    fit = score_fit(job, match, RESUME)
    assert fit.requirement_score == 3 / 4
    assert fit.missing_must_haves == []


def test_ungrounded_evidence_downgrades_the_verdict():
    job = make_job([req("R1")])
    match = assessment(m("R1", "strong", ["Managed a Kubernetes cluster of 500 nodes"]))
    fit = score_fit(job, match, RESUME)
    assert fit.requirements[0].verdict == "partial"
    assert fit.requirements[0].unverified_evidence
    assert any("downgraded" in w for w in fit.warnings)


def test_skipped_requirement_counts_as_missing():
    job = make_job([req("R1"), req("R2")])
    fit = score_fit(job, assessment(m("R1", "strong", ["Docker"])), RESUME)
    assert fit.requirement_score == 0.5
    assert "req R2" in fit.missing_must_haves


def test_final_score_blends_requirements_and_keywords():
    job = make_job([req("R1")], keywords=["Python", "Kubernetes"])
    fit = score_fit(job, assessment(m("R1", "strong", ["Docker"])), RESUME)
    # 0.85 * 1.0 + 0.15 * 0.5 = 0.925
    assert fit.score == 92 or fit.score == 93
    assert fit.missing_keywords == ["Kubernetes"]
    assert fit.band == "Strong fit"


def test_guards_flag_invented_numbers_and_keywords():
    tailored = RESUME + "\nImproved latency by 40% for 120 analysts using Kubernetes"
    assert find_new_numbers(RESUME, tailored) == ["40%"]
    assert find_new_keywords(RESUME, tailored, ["Python", "Kubernetes"]) == ["Kubernetes"]
