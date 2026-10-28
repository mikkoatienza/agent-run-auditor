"""Test helpers."""

from __future__ import annotations

from run_auditor.adapters import _event
from run_auditor.models import Run


def make_run(*events: dict[str, object]) -> Run:
    evs = [_event(dict(e)) for e in events]
    for i, e in enumerate(evs):
        e.index = i
    return Run(evs, "mem")
