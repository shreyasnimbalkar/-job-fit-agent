"""The orchestrator: runs the agents in the right order and passes data between them.

    job text ──► Job Analyst ──┐
                               ├──► Matcher ──► score (Python) ──► Writer ⇄ Reviewer ──► guards
    resume  ──► Resume Parser ─┘

* Job Analyst and Resume Parser don't depend on each other, so they run in
  parallel threads (roughly halves the wait for that stage).
* Writer and Reviewer form a feedback loop: if the Reviewer finds blocker
  issues, the Writer revises, up to `max_revisions` times.
* The control flow is plain Python, not decided by an LLM. That keeps the
  pipeline predictable, debuggable, and cheap.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable

from .agents import JobAnalystAgent, MatcherAgent, ResumeParserAgent, ReviewerAgent, WriterAgent
from .agents.base import StructuredLLM
from .schemas import JobRequirements, MatchAssessment, ResumeProfile, ReviewResult, TailoredResume
from .scoring import FitScore, find_new_keywords, find_new_numbers, score_fit

# on_event(agent_name, status, detail) - lets the CLI show progress without the
# orchestrator knowing anything about terminals.
EventHandler = Callable[[str, str, str], None]


@dataclass
class RunResult:
    job: JobRequirements
    profile: ResumeProfile
    match: MatchAssessment
    fit: FitScore
    tailored: TailoredResume | None = None
    reviews: list[ReviewResult] = field(default_factory=list)
    new_numbers: list[str] = field(default_factory=list)
    new_keywords: list[str] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)

    @property
    def approved(self) -> bool:
        return bool(self.reviews) and self.reviews[-1].approved


class Orchestrator:
    def __init__(self, llm: StructuredLLM, max_revisions: int = 2, on_event: EventHandler | None = None):
        self.analyst = JobAnalystAgent(llm)
        self.parser = ResumeParserAgent(llm)
        self.matcher = MatcherAgent(llm)
        self.writer = WriterAgent(llm)
        self.reviewer = ReviewerAgent(llm)
        self.max_revisions = max_revisions
        self.on_event = on_event or (lambda *_: None)
        self.timings: dict[str, float] = {}

    def _timed(self, label: str, fn, *args, **kwargs):
        self.on_event(label, "start", "")
        t0 = time.perf_counter()
        result = fn(*args, **kwargs)
        self.timings[label] = round(time.perf_counter() - t0, 1)
        self.on_event(label, "done", f"{self.timings[label]}s")
        return result

    def run(self, job_text: str, resume_text: str, tailor: bool = True) -> RunResult:
        self.timings = {}

        # Stage 1: independent agents in parallel.
        with ThreadPoolExecutor(max_workers=2) as pool:
            job_future = pool.submit(self._timed, self.analyst.name, self.analyst.run, job_text)
            profile_future = pool.submit(self._timed, self.parser.name, self.parser.run, resume_text)
            job, profile = job_future.result(), profile_future.result()

        # Stage 2: compare, then score deterministically.
        match = self._timed(self.matcher.name, self.matcher.run, job, profile, resume_text)
        fit = score_fit(job, match, resume_text)
        self.on_event("Scoring", "done", f"{fit.score}/100 ({fit.band})")

        result = RunResult(job=job, profile=profile, match=match, fit=fit, timings=self.timings)
        if not tailor:
            return result

        # Stage 3: write -> review -> revise loop.
        draft = self._timed(self.writer.name, self.writer.run, job, profile, match, resume_text)
        for attempt in range(self.max_revisions + 1):
            review = self._timed(
                f"{self.reviewer.name} #{attempt + 1}", self.reviewer.run, draft, resume_text, job
            )
            result.reviews.append(review)
            blockers = [i for i in review.issues if i.severity == "blocker"]
            if not blockers or attempt == self.max_revisions:
                break
            self.on_event(self.writer.name, "info", f"revising {len(blockers)} blocker(s)")
            draft = self._timed(
                f"{self.writer.name} (revision {attempt + 1})",
                self.writer.run,
                job, profile, match, resume_text, previous=draft, issues=review.issues,
            )

        # Stage 4: deterministic last line of defense against invented facts.
        result.tailored = draft
        result.new_numbers = find_new_numbers(resume_text, draft.markdown)
        result.new_keywords = find_new_keywords(resume_text, draft.markdown, job.ats_keywords)
        return result
