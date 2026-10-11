"""Write run results to disk: tailored resume, human-readable report, raw JSON."""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .orchestrator import RunResult

VERDICT_ICON = {"strong": "✅ strong", "partial": "🟡 partial", "missing": "❌ missing"}


def slugify(*parts: str) -> str:
    text = "-".join(p for p in parts if p and p.lower() != "unknown")
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "job"


def write_outputs(result: RunResult, out_root: str | Path, job_source: str, usage_line: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = Path(out_root) / f"{slugify(result.job.company, result.job.title)}-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    if result.tailored:
        (out_dir / "tailored_resume.md").write_text(result.tailored.markdown, encoding="utf-8")
    (out_dir / "fit_report.md").write_text(fit_report(result, job_source, usage_line), encoding="utf-8")
    (out_dir / "run.json").write_text(json.dumps(run_json(result, job_source), indent=2), encoding="utf-8")
    return out_dir


def run_json(result: RunResult, job_source: str) -> dict:
    return {
        "job_source": job_source,
        "job": result.job.model_dump(),
        "profile": result.profile.model_dump(),
        "match": result.match.model_dump(),
        "fit": asdict(result.fit),
        "tailored": result.tailored.model_dump() if result.tailored else None,
        "reviews": [r.model_dump() for r in result.reviews],
        "new_numbers": result.new_numbers,
        "new_keywords": result.new_keywords,
        "timings_s": result.timings,
    }


def fit_report(result: RunResult, job_source: str, usage_line: str) -> str:
    job, fit = result.job, result.fit
    lines = [
        f"# Fit Report: {job.title} at {job.company}",
        "",
        f"**Source:** {job_source}  ",
        f"**Fit score:** **{fit.score}/100** ({fit.band})  ",
        f"**Requirement coverage:** {fit.requirement_score:.0%} (weighted, must-haves count 3x)  ",
        f"**ATS keyword coverage:** {fit.keyword_score:.0%} "
        f"({len(fit.matched_keywords)}/{len(fit.matched_keywords) + len(fit.missing_keywords)})",
        "",
        f"> {job.summary}",
        "",
        "## Requirements",
        "",
        "| ID | Requirement | Importance | Verdict | Evidence from your resume |",
        "|---|---|---|---|---|",
    ]
    for r in fit.requirements:
        evidence = "<br>".join(f"“{_cell(e)}”" for e in r.evidence) or "-"
        verdict = VERDICT_ICON[r.verdict]
        if r.verdict != r.original_verdict:
            verdict += f" (was {r.original_verdict})"
        importance = "must-have" if r.importance == "must_have" else "nice-to-have"
        lines.append(f"| {r.id} | {_cell(r.text)} | {importance} | {verdict} | {evidence} |")

    lines += ["", "## Strengths", *[f"- {s}" for s in result.match.strengths]]
    lines += ["", "## Gaps", *[f"- {g}" for g in result.match.gaps]]
    if fit.missing_must_haves:
        lines += ["", "**Missing must-haves:**", *[f"- {m}" for m in fit.missing_must_haves]]
    if fit.missing_keywords:
        lines += ["", f"**Keywords not in your resume:** {', '.join(fit.missing_keywords)}"]
    lines += ["", "## Tailoring strategy", "", result.match.tailoring_strategy]

    if result.tailored:
        lines += ["", "## What changed in the tailored resume", ""]
        lines += [f"- **{c.section}:** {c.what} _(why: {c.why})_" for c in result.tailored.changes]

        lines += ["", "## Fact-check", ""]
        final = result.reviews[-1] if result.reviews else None
        status = "✅ approved by the Reviewer agent" if result.approved else "⚠️ NOT approved, read the issues below"
        lines.append(f"- Reviewer: {status} after {len(result.reviews)} review round(s)")
        if final:
            for i in final.issues:
                lines.append(f"  - [{i.severity}] “{i.quote}”: {i.problem}")
        lines.append(
            "- Numbers not found in your original resume: "
            + (", ".join(result.new_numbers) if result.new_numbers else "none ✅")
        )
        lines.append(
            "- Job keywords added that your original resume didn't mention: "
            + (", ".join(result.new_keywords) if result.new_keywords else "none ✅")
        )
        if result.new_numbers or result.new_keywords:
            lines.append("  - Check these by hand. Keep them only if they are true.")

    if fit.warnings:
        lines += ["", "## Scoring notes", *[f"- {w}" for w in fit.warnings]]

    timing = ", ".join(f"{k} {v}s" for k, v in result.timings.items())
    lines += ["", "---", f"_{usage_line}. Timings: {timing}._", ""]
    return "\n".join(lines)


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")
