import json

import pytest

from jobfit.scraper import ScrapeError, extract_job_text

LONG_DESC = "<p>We need strong Python skills.</p>" + "<li>Build REST APIs and data pipelines.</li>" * 15


def test_prefers_json_ld_job_posting():
    ld = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "Organization", "name": "Ignore me"},
            {
                "@type": "JobPosting",
                "title": "ML Platform Intern",
                "hiringOrganization": {"@type": "Organization", "name": "Northwind"},
                "description": LONG_DESC,
            },
        ],
    }
    html = f"""<html><head><script type="application/ld+json">{json.dumps(ld)}</script></head>
    <body><nav>Home | Careers</nav><p>Cookie banner</p></body></html>"""
    page = extract_job_text(html, "https://x")
    assert page.source == "json-ld"
    assert "Title: ML Platform Intern" in page.text
    assert "Company: Northwind" in page.text
    assert "Cookie banner" not in page.text


def test_falls_back_to_main_text_and_strips_noise():
    html = f"""<html><body><nav>NAV LINKS</nav><script>var x=1;</script>
    <main><h1>Backend Intern</h1>{LONG_DESC}</main><footer>FOOTER</footer></body></html>"""
    page = extract_job_text(html, "https://x")
    assert page.source == "html"
    assert "Backend Intern" in page.text
    for noise in ("NAV LINKS", "var x", "FOOTER"):
        assert noise not in page.text


def test_javascript_only_page_raises_helpful_error():
    html = '<html><body><div id="root"></div><script>render()</script></body></html>'
    with pytest.raises(ScrapeError, match="--job-file"):
        extract_job_text(html, "https://linkedin.example/job/1")
