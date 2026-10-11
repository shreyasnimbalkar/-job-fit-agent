"""Runtime settings, read from environment variables (or a local .env file)."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = "claude-opus-5-5"

# USD per million tokens. Used only to print an estimated cost after a run.
PRICING = {
    "claude-opus-5-5": {"input": 4.00, "output": 20.00, "cache_write": 5.00, "cache_read": 0.20},
    "claude-sonnet-5-5": {"input": 2.00, "output": 10.00, "cache_write": 2.50, "cache_read": 0.20},
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00, "cache_write": 1.25, "cache_read": 0.10},
}


@dataclass(frozen=True)
class Settings:
    model: str = os.getenv("JOBFIT_MODEL", DEFAULT_MODEL)
    cache_dir: str = os.getenv("JOBFIT_CACHE_DIR", ".cache")
    output_dir: str = os.getenv("JOBFIT_OUTPUT_DIR", "output")
    max_revisions: int = int(os.getenv("JOBFIT_MAX_REVISIONS", "2"))
