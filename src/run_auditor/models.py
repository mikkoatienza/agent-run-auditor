"""Core data types: normalized run events, severities and findings."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import IntEnum
from typing import Any

EVENT_TYPES = ("task", "read", "edit", "command", "claim", "message")


class Severity(IntEnum):
    """Finding severity; ordered so thresholds can be compared."""

    INFO = 1
    WARNING = 2
    ERROR = 3

    @classmethod
    def parse(cls, value: str | Severity) -> Severity:
        """Parse ``"info" | "warning" | "error"`` (case-insensitive)."""
        if isinstance(value, Severity):
            return value
        try:
            return cls[value.strip().upper()]
        except KeyError:
            raise ValueError(f"unknown severity {value!r}; use info, warning or error") from None

    def __str__(self) -> str:
        return self.name.lower()


@dataclass
class Event:
    """One normalized step of an agent run.

    ``type`` is one of :data:`EVENT_TYPES`. Which optional fields are set depends on the type:
    ``read``/``edit`` use ``path`` (and ``content`` for edits), ``command`` uses ``cmd`` and
    ``exit``, ``task``/``claim``/``message`` use ``text``.
    """

    type: str
    index: int = 0
    path: str | None = None
    content: str | None = None
    cmd: str | None = None
    exit: int | None = None
    output: str | None = None
    text: str | None = None
    ts: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Run:
    """A full agent run: ordered events plus where it came from."""

    events: list[Event]
    source: str = "<memory>"

    def of(self, *types: str) -> list[Event]:
        """Return events whose type is one of ``types``, in order."""
        return [e for e in self.events if e.type in types]

    @property
    def task(self) -> str:
        """Concatenated task text."""
        return " ".join(e.text or "" for e in self.of("task"))

    @property
    def last_edit_index(self) -> int:
        """Index of the last edit event, or ``-1`` when nothing was edited."""
        return max((e.index for e in self.of("edit")), default=-1)


@dataclass
class Finding:
    """A rule violation (or note) tied to evidence in the run."""

    rule: str
    severity: Severity
    message: str
    event_index: int | None = None
    path: str | None = None
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly dict."""
        d = asdict(self)
        d["severity"] = str(self.severity)
        return d
