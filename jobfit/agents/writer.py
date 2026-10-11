from __future__ import annotations

from ..schemas import JobRequirements, MatchAssessment, ResumeProfile, ReviewIssue, TailoredResume
from .base import UNTRUSTED_NOTE, Agent, tag

SYSTEM = f"""You are an expert resume writer tailoring a candidate's resume to one job.

The one rule that matters most: every fact in your output must come from the \
original resume. You may reorder sections and bullets, rewrite bullets for clarity \
and impact, cut less relevant content, and use the job's vocabulary when the \
underlying experience is genuinely the same (e.g. "Postgres" -> "PostgreSQL"). You \
may not add employers, titles, dates, degrees, skills, tools, or numbers that the \
original resume does not contain, and you may not inflate scope ("helped with" \
does not become "led").

How to tailor:
- Lead with the experience and projects that best match the job's must-haves.
- Open each bullet with a strong action verb; keep the original metrics.
- Put the most relevant skills first in the Skills section; drop unrelated ones if \
space is tight.
- Keep it to roughly one page (about 450-650 words).

Markdown format:
# Full Name
contact line
## Summary            (2-3 lines, only claims supported by the resume)
## Skills
## Experience         (### Title - Organization, then *dates*, then bullets)
## Projects
## Education
Omit any section the original resume doesn't have.

{UNTRUSTED_NOTE}"""


class WriterAgent(Agent):
    """Writes (and on feedback, revises) the tailored Markdown resume."""

    name = "Writer"
    effort = "high"  # the creative, quality-sensitive step gets the most thinking

    def run(
        self,
        job: JobRequirements,
        profile: ResumeProfile,
        match: MatchAssessment,
        resume_text: str,
        previous: TailoredResume | None = None,
        issues: list[ReviewIssue] | None = None,
    ) -> TailoredResume:
        context = "\n\n".join(
            [
                tag("resume", resume_text),
                tag("resume_structured", profile.model_dump_json(indent=2)),
                tag("job_requirements", job.model_dump_json(indent=2)),
                tag("match_assessment", match.model_dump_json(indent=2)),
            ]
        )
        if previous is None:
            task = "Write the tailored resume."
        else:
            feedback = "\n".join(
                f"- [{i.severity}] \"{i.quote}\": {i.problem} Fix: {i.fix}" for i in issues or []
            )
            task = (
                tag("previous_draft", previous.markdown)
                + "\n\n"
                + tag("reviewer_feedback", feedback)
                + "\n\nRevise the draft so every blocker is resolved. Keep what was already good."
            )

        # The context block is identical on the first draft and every revision, so we
        # mark it for prompt caching: revisions re-read it at ~5% of the input price.
        content = [
            {"type": "text", "text": context, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": task},
        ]
        return self.llm.structured(
            system=SYSTEM, content=content, schema=TailoredResume, effort=self.effort
        )
