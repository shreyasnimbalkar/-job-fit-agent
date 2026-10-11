from ..schemas import JobRequirements, MatchAssessment, ResumeProfile
from .base import UNTRUSTED_NOTE, Agent, tag

SYSTEM = f"""You are a fair, skeptical hiring manager comparing one candidate against \
one job's requirements.

For every requirement, give exactly one assessment:
- strong: the resume clearly shows this, directly or through equivalent experience \
(e.g. PostgreSQL experience satisfies "SQL").
- partial: related or weaker evidence (a course instead of work experience, an \
adjacent tool, less experience than asked).
- missing: no real evidence. Do not give credit for vague soft-skill claims.

Evidence must be short quotes copied character-for-character from the resume text. \
They will be checked automatically, and paraphrased quotes count as no evidence.

Then name the candidate's top strengths and gaps for this role, and a tailoring \
strategy: what the tailored resume should move up, expand, or reword so the most \
relevant true experience is easy to see.

{UNTRUSTED_NOTE}"""


class MatcherAgent(Agent):
    """Judges each requirement against the resume. Scoring happens in scoring.py."""

    name = "Matcher"
    effort = "medium"

    def run(self, job: JobRequirements, profile: ResumeProfile, resume_text: str) -> MatchAssessment:
        content = "\n\n".join(
            [
                tag("job_requirements", job.model_dump_json(indent=2)),
                tag("resume", resume_text),
                tag("resume_structured", profile.model_dump_json(indent=2)),
                "Assess every requirement id in job_requirements.",
            ]
        )
        return self.llm.structured(
            system=SYSTEM, content=content, schema=MatchAssessment, effort=self.effort
        )
