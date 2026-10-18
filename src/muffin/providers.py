"""Model providers. MUFFIN is model-agnostic: an agent only needs a `complete(system, prompt) -> str`."""
from __future__ import annotations

from typing import Callable

Completer = Callable[[str, str], str]


class AnthropicCompleter:
    """Calls the Anthropic Messages API. Requires `pip install muffin-ai[llm]` and ANTHROPIC_API_KEY.

    Note: written against the public SDK interface; not exercised against the live API in this repo's tests.
    """

    def __init__(self, model: str = "claude-sonnet-5-5", max_tokens: int = 500) -> None:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover
            raise ImportError("Install the LLM extra: pip install 'muffin-ai[llm]'") from exc
        self._client = anthropic.Anthropic()      # reads ANTHROPIC_API_KEY from the environment
        self._model = model
        self._max_tokens = max_tokens

    def __call__(self, system: str, prompt: str) -> str:
        msg = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in msg.content if getattr(block, "type", "") == "text")
