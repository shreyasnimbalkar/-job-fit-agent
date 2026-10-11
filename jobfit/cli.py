"""Command-line entry point: `python -m jobfit --resume ... --job-url ...`"""

from __future__ import annotations

import argparse
import os
import sys

import anthropic
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .config import Settings
from .llm import LLM, LLMError
from .orchestrator import Orchestrator, RunResult
from .render import write_outputs
from .resume_loader import load_resume
from .scraper import ScrapeError, fetch_job, load_job_file

console = Console()

VERDICT_STYLE = {"strong": "green", "partial": "yellow", "missing": "red"}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    settings = Settings()
    p = argparse.ArgumentParser(
        prog="jobfit",
        description="Score how well a resume fits a job posting, then tailor the resume to it.",
    )
    p.add_argument("--resume", required=True, help="Base resume (.md, .txt, or .pdf)")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--job-url", help="URL of the job posting")
    src.add_argument("--job-file", help="Job posting saved as .txt/.md/.html (for sites that block scraping)")
    p.add_argument("--score-only", action="store_true", help="Only compute the fit score; skip tailoring")
    p.add_argument("--model", default=settings.model, help=f"Claude model id (default: {settings.model})")
    p.add_argument("--max-revisions", type=int, default=settings.max_revisions,
                   help="How many times the Writer may revise after Reviewer feedback")
    p.add_argument("--out", default=settings.output_dir, help="Output folder")
    p.add_argument("--no-cache", action="store_true", help="Re-download the job page even if cached")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = Settings()

    if not os.getenv("ANTHROPIC_API_KEY"):
        console.print("[red]ANTHROPIC_API_KEY is not set.[/] Copy .env.example to .env and add your key.")
        return 2

    try:
        resume_text = load_resume(args.resume)
        if args.job_url:
            with console.status("Fetching job posting..."):
                page = fetch_job(args.job_url, settings.cache_dir, use_cache=not args.no_cache)
        else:
            page = load_job_file(args.job_file)
    except (ScrapeError, FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/] {e}")
        return 1
    console.print(f"[dim]Job text: {len(page.text):,} chars via {page.source}; resume: {len(resume_text):,} chars[/]")

    llm = LLM(model=args.model)

    def on_event(agent: str, status: str, detail: str) -> None:
        if status == "start":
            console.print(f"[cyan]▶ {agent}[/] working...")
        elif status == "done":
            console.print(f"[green]✓ {agent}[/] {detail}")
        else:
            console.print(f"[yellow]↻ {agent}[/] {detail}")

    orchestrator = Orchestrator(llm, max_revisions=args.max_revisions, on_event=on_event)
    try:
        result = orchestrator.run(page.text, resume_text, tailor=not args.score_only)
    except LLMError as e:
        console.print(f"[red]Model error:[/] {e}")
        return 1
    except anthropic.AuthenticationError:
        console.print("[red]Invalid API key.[/] Check ANTHROPIC_API_KEY.")
        return 1
    except anthropic.RateLimitError:
        console.print("[red]Rate limited even after retries.[/] Wait a minute and try again.")
        return 1
    except anthropic.APIStatusError as e:
        console.print(f"[red]API error {e.status_code}:[/] {e.message}")
        return 1
    except anthropic.APIConnectionError:
        console.print("[red]Network error.[/] Check your internet connection.")
        return 1

    cost = llm.usage.cost_usd(args.model)
    usage_line = (
        f"{llm.usage.calls} API calls, {llm.usage.input_tokens:,} input + "
        f"{llm.usage.output_tokens:,} output tokens, {llm.usage.cache_read_tokens:,} cache-read tokens"
        + (f", ~${cost:.3f}" if cost is not None else "")
    )
    out_dir = write_outputs(result, args.out, page.url, usage_line)
    print_summary(result, out_dir, usage_line)
    return 0


def print_summary(result: RunResult, out_dir, usage_line: str) -> None:
    fit = result.fit
    color = "green" if fit.score >= 75 else "yellow" if fit.score >= 55 else "red"
    console.print()
    console.print(
        Panel.fit(
            f"[bold]{result.job.title}[/] at [bold]{result.job.company}[/]\n"
            f"Fit score: [bold {color}]{fit.score}/100 - {fit.band}[/]\n"
            f"Requirements {fit.requirement_score:.0%} · Keywords {fit.keyword_score:.0%}",
            title="Job Fit",
        )
    )

    table = Table(show_lines=False)
    table.add_column("ID")
    table.add_column("Requirement", max_width=60)
    table.add_column("Need")
    table.add_column("Verdict")
    for r in fit.requirements:
        need = "must" if r.importance == "must_have" else "nice"
        table.add_row(r.id, r.text, need, f"[{VERDICT_STYLE[r.verdict]}]{r.verdict}[/]")
    console.print(table)

    if result.tailored:
        ok = "[green]approved[/]" if result.approved else "[red]not approved, check fit_report.md[/]"
        console.print(f"Reviewer: {ok} after {len(result.reviews)} round(s)")
        if result.new_numbers or result.new_keywords:
            console.print(
                "[yellow]Verify by hand:[/] new numbers "
                f"{result.new_numbers or '-'}, new keywords {result.new_keywords or '-'}"
            )
    console.print(f"[dim]{usage_line}[/]")
    console.print(f"Saved to [bold]{out_dir}[/]")


if __name__ == "__main__":
    sys.exit(main())
