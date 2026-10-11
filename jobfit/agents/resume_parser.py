from ..schemas import ResumeProfile
from .base import UNTRUSTED_NOTE, Agent, tag

SYSTEM = f"""You convert resumes into structured data with zero creativity.

Guidelines:
- Copy bullets, titles, dates, and numbers exactly as written. Do not fix, \
summarize, or improve anything.
- Skills: list every skill, tool, and language the resume names anywhere, including \
ones mentioned only inside bullets.
- If a section doesn't exist, return an empty list or empty string for it.

{UNTRUSTED_NOTE}"""


class ResumeParserAgent(Agent):
    """Turns the base resume into a structured profile the other agents can reference."""

    name = "Resume Parser"
    effort = "low"

    def run(self, resume_text: str) -> ResumeProfile:
        return self.llm.structured(
            system=SYSTEM,
            content=tag("resume", resume_text) + "\n\nConvert this resume into structured data.",
            schema=ResumeProfile,
            effort=self.effort,
        )
