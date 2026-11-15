"""The only place NorFigures talks to a language model.

The model host is separate from the data allowlist in net.py: the model never
fetches data, and data code never talks to the model (decision D19).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

MODEL = "claude-haiku-5-5"
EFFORT = "medium"
MAX_TOKENS = 8000

# Anthropic list prices for Claude Haiku 5.5 (prompts up to 100K tokens), USD
# per million tokens, as of 2026-11-15. Used only to report cost per run.
PRICE_INPUT_PER_MTOK = 0.10
PRICE_OUTPUT_PER_MTOK = 0.50

# Always the public API, unless explicitly overridden for NorFigures. This keeps
# a generic ANTHROPIC_BASE_URL set by some other tool from redirecting calls.
BASE_URL = os.environ.get("NORFIGURES_ANTHROPIC_BASE_URL", "https://api.anthropic.com")


class AgentError(Exception):
    """The agent could not run or returned something unusable. Exit code 3."""


@dataclass(frozen=True)
class LLMResult:
    text: str
    model: str
    stop_reason: str
    input_tokens: int
    output_tokens: int

    @property
    def cost_usd(self) -> float:
        return (self.input_tokens * PRICE_INPUT_PER_MTOK
                + self.output_tokens * PRICE_OUTPUT_PER_MTOK) / 1_000_000


def complete_json(system: str, user: str, schema: dict, model: str = MODEL) -> LLMResult:
    """One structured-output call. Raises AgentError on any failure."""
    try:
        import anthropic
    except ImportError as e:
        raise AgentError("the agent steps need the Anthropic SDK: pip install 'norfigures[agents]'") from e

    try:
        client = anthropic.Anthropic(base_url=BASE_URL)
        resp = client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": EFFORT,
                           "format": {"type": "json_schema", "schema": schema}},
        )
    except TypeError as e:
        # The SDK raises TypeError before any request when it finds no credentials.
        if "authentication" not in str(e).lower():
            raise
        raise AgentError("no Anthropic API key found: set ANTHROPIC_API_KEY "
                         "(or run `ant auth login`)") from e
    except anthropic.AuthenticationError as e:
        raise AgentError("Anthropic API key missing or invalid (set ANTHROPIC_API_KEY)") from e
    except anthropic.APIConnectionError as e:
        raise AgentError(f"could not reach the Anthropic API: {e}") from e
    except anthropic.APIStatusError as e:
        raise AgentError(f"Anthropic API error {e.status_code}: {e.message}") from e
    except anthropic.AnthropicError as e:
        raise AgentError(f"Anthropic SDK error: {e}") from e

    if resp.stop_reason == "refusal":
        raise AgentError("the model declined the request (stop_reason: refusal)")
    if resp.stop_reason == "max_tokens":
        raise AgentError("the model's answer was cut off (max_tokens); the text may be too long")
    text = next((b.text for b in resp.content if b.type == "text"), None)
    if text is None:
        raise AgentError(f"the model returned no text (stop_reason: {resp.stop_reason})")
    return LLMResult(text, resp.model, resp.stop_reason,
                     resp.usage.input_tokens, resp.usage.output_tokens)
