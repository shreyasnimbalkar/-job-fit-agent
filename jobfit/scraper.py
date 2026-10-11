"""Fetch a job posting and turn it into clean text.

Strategy, in order:
  1. Look for schema.org `JobPosting` JSON-LD. Most applicant tracking systems
     (Greenhouse, Lever, Workday, many company career sites) embed it for
     Google Jobs, and it is far cleaner than scraping visible HTML.
  2. Otherwise strip navigation/scripts/footers and take the main page text.

Results are cached on disk by URL hash so repeated runs don't re-download.
Pages rendered entirely by JavaScript (e.g. LinkedIn) return almost no text to
a plain HTTP client; in that case we raise ScrapeError and the user can paste
the posting into a file and pass --job-file instead.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

MIN_USEFUL_CHARS = 300

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/129.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

NOISE_TAGS = ["script", "style", "noscript", "svg", "nav", "header", "footer", "aside", "form", "iframe"]


class ScrapeError(RuntimeError):
    pass


@dataclass
class JobPage:
    url: str
    text: str
    source: str  # "json-ld", "html", or "file"


def fetch_job(url: str, cache_dir: str | Path = ".cache", use_cache: bool = True) -> JobPage:
    cache_file = Path(cache_dir) / "jobs" / f"{hashlib.sha256(url.encode()).hexdigest()[:16]}.json"
    if use_cache and cache_file.exists():
        return JobPage(**json.loads(cache_file.read_text(encoding="utf-8")))

    try:
        resp = httpx.get(url, headers=HEADERS, follow_redirects=True, timeout=20)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise ScrapeError(f"Could not download {url}: {e}") from e

    page = extract_job_text(resp.text, url)

    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(asdict(page), ensure_ascii=False), encoding="utf-8")
    return page


def load_job_file(path: str | Path) -> JobPage:
    text = Path(path).read_text(encoding="utf-8")
    if Path(path).suffix.lower() in {".html", ".htm"}:
        return extract_job_text(text, str(path))
    return JobPage(url=str(path), text=clean_text(text), source="file")


def extract_job_text(html: str, url: str) -> JobPage:
    soup = BeautifulSoup(html, "html.parser")

    posting = _find_json_ld_job(soup)
    if posting:
        text = _format_json_ld(posting)
        if len(text) >= MIN_USEFUL_CHARS:
            return JobPage(url=url, text=text, source="json-ld")

    for tag in soup(NOISE_TAGS):
        tag.decompose()
    root = soup.find("main") or soup.find("article") or soup.body or soup
    text = clean_text(root.get_text("\n"))

    if len(text) < MIN_USEFUL_CHARS:
        raise ScrapeError(
            f"Only found {len(text)} characters of text at {url}. The page is probably "
            "rendered with JavaScript or behind a login. Copy the job description into a "
            ".txt file and run again with --job-file <path>."
        )
    return JobPage(url=url, text=text, source="html")


def clean_text(text: str) -> str:
    lines = [re.sub(r"[ \t\xa0]+", " ", line).strip() for line in text.splitlines()]
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _find_json_ld_job(soup: BeautifulSoup) -> dict | None:
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except json.JSONDecodeError:
            continue
        for item in _walk_json_ld(data):
            types = item.get("@type")
            types = types if isinstance(types, list) else [types]
            if "JobPosting" in types:
                return item
    return None


def _walk_json_ld(data):
    """JSON-LD can be a single object, a list, or nested under @graph."""
    if isinstance(data, list):
        for x in data:
            yield from _walk_json_ld(x)
    elif isinstance(data, dict):
        yield data
        if "@graph" in data:
            yield from _walk_json_ld(data["@graph"])


def _format_json_ld(p: dict) -> str:
    org = p.get("hiringOrganization") or {}
    org_name = org.get("name", "") if isinstance(org, dict) else str(org)
    description_html = p.get("description", "")
    description = clean_text(BeautifulSoup(description_html, "html.parser").get_text("\n"))

    parts = [
        f"Title: {p.get('title', '')}",
        f"Company: {org_name}",
        f"Employment type: {p.get('employmentType', '')}",
        "",
        description,
    ]
    for key in ("qualifications", "skills", "responsibilities", "experienceRequirements"):
        value = p.get(key)
        if isinstance(value, str) and value.strip():
            parts += ["", f"{key.title()}:", clean_text(BeautifulSoup(value, "html.parser").get_text("\n"))]
    return "\n".join(parts).strip()
