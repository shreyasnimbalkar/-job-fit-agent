"""Thin wrapper around the Anthropic SDK.

All agents talk to Claude through `LLM.structured()`, which:
  * sends a system prompt + user content,
  * forces the reply to match a Pydantic schema (structured outputs),
  * sets the reasoning effort per agent,
  * opts into server-side refusal fallbacks,
  * and keeps a running total of token usage so we can report cost.

Keeping this in one place means agents never deal with raw API details, and
tests can swap in a fake LLM with the same `structured()` signature.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Literal, TypeVar

import anthropic
from pydantic import BaseModel

from .config import PRICING

T = TypeVar("T", bound=BaseModel)
Effort = Literal["low", "medium", "high", "xhigh", "max"]

# Server-side fallback: if a safety classifier declines a request (rare, and
# sometimes a false positive), the API retries it on a recommended fallback
# model instead of failing the whole pipeline.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMError(RuntimeError):
    """Raised when Claude returns no usable structured output."""


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    calls: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, u) -> None:
        with self._lock:
            self.calls += 1
            self.input_tokens += u.input_tokens or 0
            self.output_tokens += u.output_tokens or 0
            self.cache_write_tokens += getattr(u, "cache_creation_input_tokens", 0) or 0
            self.cache_read_tokens += getattr(u, "cache_read_input_tokens", 0) or 0

    def cost_usd(self, model: str) -> float | None:
        p = PRICING.get(model)
        if p is None:
            return None
        return (
            self.input_tokens * p["input"]
            + self.output_tokens * p["output"]
            + self.cache_write_tokens * p["cache_write"]
            + self.cache_read_tokens * p["cache_read"]
        ) / 1_000_000


class LLM:
    def __init__(self, model: str, client: anthropic.Anthropic | None = None):
        self.model = model
        # Anthropic() reads ANTHROPIC_API_KEY from the environment.
        # max_retries makes the SDK retry 429/5xx/network errors with backoff.
        self.client = client or anthropic.Anthropic(max_retries=4)
        self.usage = Usage()

    def structured(
        self,
        *,
        system: str,
        content: str | list[dict],
        schema: type[T],
        effort: Effort = "medium",
        max_tokens: int = 16000,
    ) -> T:
        response = self.client.beta.messages.parse(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": content}],
            output_format=schema,
            output_config={"effort": effort},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
        self.usage.add(response.usage)

        # Always check why the model stopped before trusting the content.
        if response.stop_reason == "refusal":
            category = getattr(response.stop_details, "category", None)
            raise LLMError(f"Claude declined the request (category: {category}).")
        if response.stop_reason == "max_tokens":
            raise LLMError(
                f"Output was cut off at max_tokens={max_tokens} while producing "
                f"{schema.__name__}. Try again with a shorter input."
            )
        if response.parsed_output is None:
            raise LLMError(f"No parseable {schema.__name__} in the response.")
        return response.parsed_output
