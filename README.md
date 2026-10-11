# Job Fit Agent

[![tests](https://github.com/shreyasnimbalkar/job-fit-agent/actions/workflows/tests.yml/badge.svg)](https://github.com/shreyasnimbalkar/job-fit-agent/actions/workflows/tests.yml)

A command-line tool that reads a job posting and your resume, scores how well you
fit, and writes a tailored version of the resume without making anything up.

It is split into five Claude agents with narrow jobs. The Job Analyst pulls the
requirements out of the posting and the Resume Parser structures your resume (these
two run in parallel). The Matcher judges each requirement as strong, partial or
missing and has to quote the resume as evidence. The Writer drafts the tailored
resume and the Reviewer fact-checks it against the original, sending it back for
revision until there are no blocking issues.

The fit score is not something the model makes up. Python computes it from the
Matcher's verdicts with a fixed formula, after checking that every quoted piece of
evidence actually appears in the resume. A last pass flags any number or job keyword
in the tailored resume that the original never mentioned. [DESIGN.md](DESIGN.md) has
the formula and the reasoning behind these choices.

## Quick start

```powershell
git clone https://github.com/shreyasnimbalkar/job-fit-agent.git
cd job-fit-agent
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env          # add your Anthropic API key

# bundled example
python -m jobfit --resume examples/sample_resume.md --job-file examples/sample_job.txt

# a real posting
python -m jobfit --resume my_resume.pdf --job-url https://boards.greenhouse.io/company/jobs/123
```

Some sites (LinkedIn, some Workday pages) need a login or build the page with
JavaScript, so a plain download gets almost no text. The tool notices this and asks
you to paste the posting into a `.txt` file and pass `--job-file` instead.

## Options

```
--resume PATH          base resume (.md, .txt or .pdf)
--job-url URL          the posting to fetch
--job-file PATH        the posting saved as .txt/.md/.html
--score-only           only compute the fit score (3 API calls instead of 5 or more)
--max-revisions N      how many times the Writer may revise after review (default 2)
--model ID             Claude model (default claude-opus-5-5)
--out DIR              output folder (default output/)
--no-cache             download the job page again instead of using the cached copy
```

## Output

Each run writes a folder `output/<company>-<title>-<timestamp>/` with:

- `tailored_resume.md`
- `fit_report.md`: the score, a requirement-by-requirement table with evidence, gaps,
  what changed and why, the fact-check results, and token usage and cost
- `run.json`: every agent's raw structured output, for debugging

## Tests

```powershell
pytest -q
```

14 offline tests. A `FakeLLM` stands in for the API, so they check the agent order,
the revision loop, the scoring math, the evidence checks, the scraper and the report
output without spending anything.

## Layout

```
jobfit/
  cli.py            command-line interface (rich for the terminal output)
  orchestrator.py   runs the agents: parallel first stage, then the revision loop
  agents/           one file per agent: system prompt plus input building
  schemas.py        Pydantic models passed between agents
  llm.py            Anthropic SDK wrapper: structured outputs, effort, usage and cost
  scraper.py        download, JSON-LD extraction, HTML cleanup, disk cache
  scoring.py        fit score, evidence checks, guards for new numbers and keywords
  render.py         writes the resume, report and JSON
  resume_loader.py  reads .md, .txt or .pdf resumes
examples/           a sample resume and job posting
tests/
```

## Limitations

- JavaScript-only pages need `--job-file`. A headless browser such as Playwright would
  fix that.
- No `.docx` input or output yet.
- The score weights (must-haves count 3x, 85/15 split between requirements and
  keywords) are hand-picked. Calibrating them would need real application outcomes.

## License

MIT
