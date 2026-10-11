from ..schemas import JobRequirements, ReviewResult, TailoredResume
from .base import UNTRUSTED_NOTE, Agent, tag

SYSTEM = f"""You are a strict fact-checker reviewing a tailored resume before it is \
sent to an employer. You compare the draft line by line against the original resume.

Report a blocker when the draft:
- states a skill, tool, employer, title, date, degree, or number that is not in the \
original resume;
- inflates scope or ownership beyond what the original supports ("assisted" -> "led");
- drops the candidate's name or contact line, or breaks the Markdown structure.

Report a minor issue for weak wording, a relevant original bullet that was cut, or \
an important job keyword the candidate truly has but the draft doesn't show.

Set approved to true only if there are no blockers. Do not invent problems: an \
accurate rewording of an original bullet is fine.

{UNTRUSTED_NOTE}"""


class ReviewerAgent(Agent):
    """Independent critic that catches fabrication before the user sees the resume."""

    name = "Reviewer"
    effort = "medium"

    def run(self, draft: TailoredResume, resume_text: str, job: JobRequirements) -> ReviewResult:
        content = "\n\n".join(
            [
                tag("original_resume", resume_text),
                tag("tailored_draft", draft.markdown),
                tag("job_requirements", job.model_dump_json(indent=2)),
                "Review the tailored draft.",
            ]
        )
        result = self.llm.structured(
            system=SYSTEM, content=content, schema=ReviewResult, effort=self.effort
        )
        # Don't trust the model's own `approved` flag blindly: recompute it.
        result.approved = not any(i.severity == "blocker" for i in result.issues)
        return result
