# Design notes

## Pipeline

```
job text --> Job Analyst ---+
                            +--> Matcher --> score (Python) --> Writer <--> Reviewer --> guards
resume   --> Resume Parser -+
```

The order is fixed in `orchestrator.py`. The model never decides what happens next,
because the steps are known in advance and a fixed order is cheaper, faster and easier
to debug than letting an agent plan its own route. The Job Analyst and Resume Parser
don't depend on each other, so they run in two threads; the work is waiting on the
network, so Python threads are fine here.

| Agent | Produces | Effort |
|---|---|---|
| Job Analyst | `JobRequirements`: requirements (must-have or nice-to-have), ATS keywords | low |
| Resume Parser | `ResumeProfile`: experience, projects, skills, copied verbatim | low |
| Matcher | `MatchAssessment`: strong/partial/missing per requirement, with quotes | medium |
| Writer | `TailoredResume`: Markdown plus a list of changes and reasons | high |
| Reviewer | `ReviewResult`: blocker and minor issues | medium |

Every agent returns a Pydantic model through the API's structured outputs, so the
next step always gets validated data instead of free text it has to parse. Effort is
set per agent: extraction is easy and runs at `low`; writing is the step where quality
matters, so it gets `high`.

## Scoring

```
requirement_score = sum(weight * value) / sum(weight)
    weight: must_have = 3, nice_to_have = 1
    value:  strong = 1.0, partial = 0.5, missing = 0

keyword_score = ATS keywords found in the resume / all ATS keywords

fit = round(100 * (0.85 * requirement_score + 0.15 * keyword_score))
bands: 75+ strong fit, 55-74 good fit, 35-54 stretch, below 35 weak fit
```

Before the formula runs, every strong or partial verdict needs at least one evidence
quote that really appears in the resume (case, Markdown symbols and light rewording
are tolerated; 80% of the quote's words must be present). If none does, the verdict
drops one level. A requirement the Matcher skipped counts as missing.

The model makes the judgment calls and code does the arithmetic. A score the model
invents directly changes from run to run and can't be explained; this one can be
traced to individual requirements and quotes. Keyword overlap only gets 15% because it
can't tell daily use of a tool from a single mention.

Keyword matching is whole-word and treats `+` and `#` as part of a word, so "C" does
not match inside "C++" and "Java" does not match "JavaScript".

## Keeping the resume honest

There are four separate checks, and the last one is plain code:

1. The Writer's prompt forbids adding employers, titles, dates, skills, tools or
   numbers, and inflating scope ("helped with" does not become "led").
2. The Matcher's evidence quotes are verified against the resume.
3. A separate Reviewer agent compares the draft with the original line by line. Its
   `approved` flag is recomputed in code from whether any blocker issues exist, rather
   than trusted.
4. `find_new_numbers` and `find_new_keywords` list any number (like "40%") or job
   keyword that is in the tailored resume but not in the original. The report tells
   the user to check those by hand.

## Other details

- Scraped and uploaded text goes inside XML tags (`<job_posting>`, `<resume>`) and every
  agent is told to treat tagged content as data, never as instructions. This lowers
  the risk of prompt injection from a job page; it doesn't remove it, which is one more
  reason the score is computed in code.
- The scraper looks for schema.org `JobPosting` JSON-LD first. Most applicant tracking
  systems embed it for Google Jobs and it is much cleaner than the visible page. If
  it's missing, BeautifulSoup strips navigation, scripts and footers and keeps the main
  text. Pages are cached on disk by a hash of the URL.
- The Writer's context block (resume, profile, requirements, assessment) is the same
  on every revision, so it is marked for prompt caching and only the feedback changes.
- `LLM.structured()` checks the stop reason before trusting the output: a refusal or
  a reply cut off at `max_tokens` raises `LLMError` with a clear message. The SDK
  retries 429 and 5xx errors itself (`max_retries=4`), and refused requests are retried
  on a fallback model (`fallbacks="default"`).
- Token usage is summed across calls and priced with the per-model table in
  `config.py` to print an estimated cost per run.
