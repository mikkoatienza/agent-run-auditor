"""LLM provider interface with optional OpenAI / Anthropic adapters.

Provider SDKs are optional extras and are imported lazily, so the package works
(and its tests run) with no network and no API keys via :class:`OfflineLLM`.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Completion:
    """A model response plus the token usage reported by the provider."""

    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = "offline"


@runtime_checkable
class LLM(Protocol):
    """Anything that can turn a prompt into a :class:`Completion`."""

    def complete(self, prompt: str, *, system: str = "", max_tokens: int = 1024) -> Completion:
        """Return a completion for ``prompt``."""
        ...


class OfflineLLM:
    """Deterministic stand-in for tests, demos and air-gapped use.

    ``responder`` maps a prompt to text. The default echoes a stable digest so
    output is reproducible. Token counts are estimated as ``len(text) // 4``.
    """

    def __init__(self, responder: Callable[[str], str] | None = None) -> None:
        self._responder = responder or (
            lambda p: "offline:" + hashlib.sha256(p.encode()).hexdigest()[:12]
        )

    def complete(self, prompt: str, *, system: str = "", max_tokens: int = 1024) -> Completion:
        text = self._responder(prompt)
        return Completion(text, len(prompt) // 4, len(text) // 4, "offline")


class OpenAILLM:
    """OpenAI Chat Completions adapter. Needs ``pip install '.[openai]'`` and ``OPENAI_API_KEY``."""

    def __init__(self, model: str | None = None) -> None:
        from openai import OpenAI

        self.model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        self._client = OpenAI()

    def complete(self, prompt: str, *, system: str = "", max_tokens: int = 1024) -> Completion:
        messages = ([{"role": "system", "content": system}] if system else []) + [
            {"role": "user", "content": prompt}
        ]
        r = self._client.chat.completions.create(
            model=self.model, messages=messages, max_tokens=max_tokens
        )
        u = r.usage
        return Completion(
            r.choices[0].message.content or "",
            getattr(u, "prompt_tokens", 0),
            getattr(u, "completion_tokens", 0),
            self.model,
        )


class AnthropicLLM:
    """Anthropic Messages adapter. Needs the ``[anthropic]`` extra and ``ANTHROPIC_API_KEY``."""

    def __init__(self, model: str | None = None) -> None:
        import anthropic

        self.model = model or os.environ.get("ANTHROPIC_MODEL", "claude-3-5-haiku-latest")
        self._client = anthropic.Anthropic()

    def complete(self, prompt: str, *, system: str = "", max_tokens: int = 1024) -> Completion:
        r = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system or None,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(getattr(b, "text", "") for b in r.content)
        return Completion(text, r.usage.input_tokens, r.usage.output_tokens, self.model)


def get_llm(name: str | None = None) -> LLM:
    """Build a provider by name (``offline``, ``openai``, ``anthropic``).

    Defaults to the ``LLM_PROVIDER`` environment variable, then ``offline``.
    """
    name = (name or os.environ.get("LLM_PROVIDER", "offline")).lower()
    if name == "openai":
        return OpenAILLM()
    if name == "anthropic":
        return AnthropicLLM()
    if name == "offline":
        return OfflineLLM()
    raise ValueError(f"unknown LLM provider: {name!r}")
