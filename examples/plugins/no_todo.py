"""Example plugin: flag edits that introduce TODO/FIXME markers."""

from __future__ import annotations

from typing import Any

from run_auditor.models import Run, Severity
from run_auditor.rules import Context, Hit, rule


@rule("no-new-todos", Severity.INFO, "Edits should not add TODO/FIXME markers")
def no_new_todos(run: Run, opts: dict[str, Any], ctx: Context) -> list[Hit]:
    """Report each edit whose content contains TODO or FIXME."""
    return [
        Hit(f"{e.path} adds a TODO/FIXME", e, e.path)
        for e in run.of("edit")
        if e.content and ("TODO" in e.content or "FIXME" in e.content)
    ]
