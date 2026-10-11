from ..schemas import JobRequirements
from .base import UNTRUSTED_NOTE, Agent, tag

SYSTEM = f"""You are a technical recruiter who turns messy job postings into a clean, \
structured list of requirements.

Guidelines:
- Split compound lines into separate requirements ("Python and SQL" -> two requirements).
- Mark a requirement must_have when the posting calls it required, minimum, basic, or \
must; mark it nice_to_have when it says preferred, bonus, plus, or nice to have. If the \
posting doesn't say, use must_have for items in the main qualifications list.
- Ignore benefits, EEO statements, company boilerplate, and salary text.
- ats_keywords are exact terms an applicant tracking system would match on: languages, \
frameworks, tools, cloud services, methods. Prefer the posting's own spelling.

{UNTRUSTED_NOTE}"""


class JobAnalystAgent(Agent):
    """Reads the raw posting and extracts structured requirements."""

    name = "Job Analyst"
    effort = "low"  # pure extraction; low effort is fast and cheap

    def run(self, job_text: str) -> JobRequirements:
        return self.llm.structured(
            system=SYSTEM,
            content=tag("job_posting", job_text) + "\n\nExtract the requirements from this posting.",
            schema=JobRequirements,
            effort=self.effort,
        )
