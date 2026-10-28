"""Find verifiable claims in an agent's messages.

A *claim* is something the agent says it did ("all tests pass", "the build is green") that
the log can confirm or contradict. :class:`KeywordClaimDetector` works offline;
:class:`LLMClaimDetector` asks a model and falls back to keywords on bad output.
"""

from __future__ import annotations

import json
import re
from typing import Protocol, runtime_checkable

from .llm import LLM

#: Claim kind -> regex that recognises it in prose.
CLAIM_PATTERNS: dict[str, str] = {
    "tests": r"\b(all\s+)?tests?\s+(now\s+)?(pass|passing|passed|green)\b|\btests?\s+are\s+green",
    "build": r"\bbuild\s+(now\s+)?(passes|succeeds|succeeded|works|is\s+green)\b",
    "lint": r"\b(lint|linter|linting)\s+(is\s+)?(clean|passes|passing)\b|\bno\s+lint\s+errors\b",
    "types": r"\b(type\s*check(s|ing)?|mypy|tsc)\s+(is\s+)?(clean|passes|passing)\b",
}

#: Claim kind -> regex that a command must match to count as evidence.
EVIDENCE_COMMANDS: dict[str, str] = {
    "tests": r"\b(pytest|jest|vitest|mocha|go\s+test|cargo\s+test|npm\s+(run\s+)?test|"
    r"pnpm\s+test|yarn\s+test|unittest|rspec|phpunit|make\s+test|tox|nox)\b",
    "build": r"\b(build|compile|make|cargo\s+build|go\s+build|tsc)\b",
    "lint": r"\b(ruff|flake8|eslint|pylint|golangci-lint|clippy|lint)\b",
    "types": r"\b(mypy|pyright|tsc|typecheck)\b",
}


@runtime_checkable
class ClaimDetector(Protocol):
    """Returns the claim kinds (keys of :data:`EVIDENCE_COMMANDS`) made in ``text``."""

    def detect(self, text: str) -> set[str]: ...


class KeywordClaimDetector:
    """Regex detector over :data:`CLAIM_PATTERNS`. Deterministic and free."""

    def __init__(self, patterns: dict[str, str] | None = None) -> None:
        self.patterns = {k: re.compile(v, re.I) for k, v in (patterns or CLAIM_PATTERNS).items()}

    def detect(self, text: str) -> set[str]:
        """Return claim kinds whose pattern matches."""
        # Ignore negated statements such as "tests do not pass yet".
        cleaned = re.sub(r"\b(not|n't|never|fail\w*)\b[^.]*", " ", text, flags=re.I)
        return {k for k, rx in self.patterns.items() if rx.search(cleaned)}


class LLMClaimDetector:
    """Ask an LLM which claims a message makes; falls back to keywords on unusable output."""

    PROMPT = (
        "Which of these verifiable claims does the message make? Kinds: {kinds}. "
        'Answer with a JSON list of kinds only, e.g. ["tests"]. Message:\n{text}'
    )

    def __init__(self, llm: LLM, fallback: ClaimDetector | None = None) -> None:
        self.llm = llm
        self.fallback = fallback or KeywordClaimDetector()

    def detect(self, text: str) -> set[str]:
        """Return claim kinds, using the model when its answer parses."""
        prompt = self.PROMPT.format(kinds=", ".join(EVIDENCE_COMMANDS), text=text)
        reply = self.llm.complete(prompt, max_tokens=50).text
        match = re.search(r"\[.*?\]", reply, re.S)
        if match:
            try:
                kinds = json.loads(match.group(0))
            except json.JSONDecodeError:
                kinds = None
            if isinstance(kinds, list):
                return {str(k) for k in kinds if k in EVIDENCE_COMMANDS}
        return self.fallback.detect(text)
