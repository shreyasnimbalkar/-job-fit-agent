"""Load the base resume from Markdown, plain text, or PDF."""

from pathlib import Path

from pypdf import PdfReader


def load_resume(path: str | Path) -> str:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Resume not found: {path}")

    if path.suffix.lower() == ".pdf":
        reader = PdfReader(str(path))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    elif path.suffix.lower() in {".md", ".txt", ".markdown"}:
        text = path.read_text(encoding="utf-8")
    else:
        raise ValueError(f"Unsupported resume format '{path.suffix}'. Use .md, .txt, or .pdf.")

    text = text.strip()
    if len(text) < 200:
        raise ValueError(
            f"Only {len(text)} characters were read from {path}. If this is a scanned PDF, "
            "export it as text or Markdown first."
        )
    return text
