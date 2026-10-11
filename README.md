# Job Fit & Resume Tailoring Agent

[![tests](https://github.com/shreyasnimbalkar/job-fit-agent/actions/workflows/tests.yml/badge.svg)](https://github.com/shreyasnimbalkar/job-fit-agent/actions/workflows/tests.yml)
![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

A terminal-based, multi-agent AI system. Give it your base resume and a job posting URL. It:

1. **crawls** the posting (schema.org JSON-LD first, cleaned HTML as a fallback),
2. **extracts** the requirements, separating must-haves from nice-to-haves,
3. **compares** each requirement to your resume, citing quoted evidence,
4. **scores** your fit 0-100 with a transparent, deterministic formula,
5. **writes** a tailored Markdown resume, and
6. **fact-checks** that resume with an independent Reviewer agent plus code-level guards, so it never invents experience.

```
                 ┌──────────────┐
  job URL ─────► │ Job Analyst  │──┐
                 └──────────────┘  │   ┌─────────┐   ┌──────────────┐   ┌────────┐   ┌──────────┐
                                   ├──►│ Matcher │──►│ Score (code) │──►│ Writer │⇄─►│ Reviewer │──► guards ──► output/
                 ┌──────────────┐  │   └─────────┘   └──────────────┘   └────────┘   └──────────┘
  resume ──────► │ Resume Parser│──┘
                 └──────────────┘
         (parallel)                                                  (revise until no blockers, max N)
```

## Quick start

```bash
git clone https://github.com/shreyasnimbalkar/job-fit-agent.git
cd job-fit-agent
python -m venv .venv
.venv\Scripts\activate            # Windows   (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env            # then put your Anthropic API key in .env

# Try it on the bundled example
python -m jobfit --resume examples/sample_resume.md --job-file examples/sample_job.txt

# Use a real posting
python -m jobfit --resume my_resume.pdf --job-url https://boards.greenhouse.io/company/jobs/123
```

### Options

| Flag | What it does |
|---|---|
| `--resume PATH` | Base resume: `.md`, `.txt`, or `.pdf` |
| `--job-url URL` / `--job-file PATH` | The posting. Use `--job-file` for sites that need a login or render with JavaScript (LinkedIn, some Workday pages): paste the text into a `.txt` file |
| `--score-only` | Only compute the fit score (3 API calls instead of 5+) |
| `--max-revisions N` | How many times the Writer may revise after Reviewer feedback (default 2) |
| `--model ID` | Claude model (default `claude-opus-5-5`) |
| `--no-cache` | Re-download the job page instead of using the on-disk cache |

### Output

Each run creates `output/<company>-<title>-<timestamp>/` containing:

- `tailored_resume.md`: the new resume
- `fit_report.md`: score, requirement-by-requirement table with evidence, gaps, what changed and why, fact-check results, tokens and cost
- `run.json`: every agent's raw structured output, for debugging

## Design decisions

| Decision | Why |
|---|---|
| **Specialized agents** instead of one giant prompt | Each agent has one job, a focused prompt, and a typed output, so it's easier to debug, test, and improve one step at a time |
| **Structured outputs** (Pydantic schemas) | Agents hand each other validated JSON, not free text that has to be parsed |
| **Score computed in Python**, not by the LLM | The LLM judges each requirement; a fixed formula turns those judgments into a number. Explainable and consistent |
| **Evidence verification** | Quotes the Matcher cites must actually appear in the resume, or the verdict is downgraded |
| **Writer ⇄ Reviewer loop** | A separate critic catches fabricated claims; the Writer revises until there are no blockers |
| **Deterministic guards** | Numbers or job keywords in the output that weren't in the original resume get flagged for a human to check |
| **Per-agent effort levels** | Extraction runs at `low` effort (fast and cheap); writing runs at `high` (quality) |
| **Parallel first stage** | Job analysis and resume parsing are independent, so they run at the same time |
| **Prompt caching** | The Writer's large context block is cached, so revisions re-read it at a fraction of the price |
| **Prompt-injection hygiene** | Scraped text goes inside XML tags, and every agent is told to treat it as data, not instructions |

## Project layout

```
jobfit/
  cli.py            command-line interface and terminal output (rich)
  orchestrator.py   runs the agents in order, parallel stage, revision loop
  agents/           one file per agent: prompt + typed input/output
  schemas.py        Pydantic data contracts between agents
  llm.py            Anthropic SDK wrapper: structured outputs, effort, fallbacks, usage/cost
  scraper.py        fetch + JSON-LD extraction + HTML cleanup + disk cache
  scoring.py        deterministic scoring, evidence verification, fabrication guards
  render.py         writes the Markdown report, resume, and JSON
tests/              14 offline tests (fake LLM, no API key needed)
```

## Tests

```bash
pytest -q
```

The tests use a `FakeLLM`, so they run offline for free. They cover the scoring math, keyword matching edge cases (`C` vs `C++`), hallucinated-evidence downgrades, the scraper's JSON-LD and fallback paths, and the full orchestration, including the revision loop.

## Limitations and next steps

- JavaScript-rendered pages need `--job-file` (a headless browser such as Playwright would fix this)
- No `.docx` input yet
- The score weights (must-have = 3x, 85/15 requirement/keyword split) are hand-picked; a labeled set of past applications could calibrate them
- Possible next steps: batch mode over many URLs, a cover letter agent, an evaluation set to measure fabrication rate
