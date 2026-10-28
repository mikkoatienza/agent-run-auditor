"""Render findings as JSON, Markdown or SARIF 2.1.0."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from . import __version__
from .models import Finding, Severity
from .rules import REGISTRY

SARIF_LEVEL = {Severity.INFO: "note", Severity.WARNING: "warning", Severity.ERROR: "error"}
ICON = {Severity.INFO: "ℹ️", Severity.WARNING: "⚠️", Severity.ERROR: "❌"}


def summary(findings: list[Finding]) -> dict[str, int]:
    """Counts per severity name."""
    c = Counter(str(f.severity) for f in findings)
    return {s: c.get(s, 0) for s in ("error", "warning", "info")}


def to_json(results: dict[str, list[Finding]]) -> str:
    """JSON document: ``{"runs": {source: [finding...]}, "summary": {...}}``."""
    all_f = [f for fs in results.values() for f in fs]
    doc = {
        "tool": "agent-run-auditor",
        "version": __version__,
        "summary": summary(all_f),
        "runs": {src: [f.to_dict() for f in fs] for src, fs in results.items()},
    }
    return json.dumps(doc, indent=2)


def to_markdown(results: dict[str, list[Finding]]) -> str:
    """A Markdown report suitable for a PR comment or job summary."""
    all_f = [f for fs in results.values() for f in fs]
    s = summary(all_f)
    lines = [
        "## Agent run audit",
        "",
        f"**{s['error']}** errors · **{s['warning']}** warnings · **{s['info']}** info "
        f"across {len(results)} run(s)",
        "",
    ]
    for src, fs in results.items():
        lines.append(f"### `{src}` {'✅ clean' if not fs else ''}".rstrip())
        if fs:
            lines += ["", "| | Rule | Event | Finding |", "|---|---|---|---|"]
            for f in fs:
                ev = "" if f.event_index is None else f"#{f.event_index}"
                msg = f.message.replace("|", "\\|")
                lines.append(f"| {ICON[f.severity]} | `{f.rule}` | {ev} | {msg} |")
        lines.append("")
    return "\n".join(lines)


def to_sarif(results: dict[str, list[Finding]]) -> str:
    """SARIF 2.1.0 log for GitHub code scanning and other SARIF viewers.

    Findings with a file path point at that file; others point at the run log, with the
    event index as the line number (1-based) for jsonl logs.
    """
    rule_ids = sorted({f.rule for fs in results.values() for f in fs})
    rules = []
    for rid in rule_ids:
        spec = REGISTRY.get(rid)
        rules.append(
            {
                "id": rid,
                "shortDescription": {"text": spec.description if spec else rid},
                "defaultConfiguration": {
                    "level": SARIF_LEVEL[spec.severity] if spec else "warning"
                },
            }
        )
    out: list[dict[str, Any]] = []
    for src, fs in results.items():
        for f in fs:
            region: dict[str, Any] = {}
            uri = f.path or src
            if not f.path and f.event_index is not None:
                region = {"startLine": f.event_index + 1}
            loc: dict[str, Any] = {"physicalLocation": {"artifactLocation": {"uri": uri}}}
            if region:
                loc["physicalLocation"]["region"] = region
            out.append(
                {
                    "ruleId": f.rule,
                    "level": SARIF_LEVEL[f.severity],
                    "message": {"text": f"{f.message} (run: {src})"},
                    "locations": [loc],
                }
            )
    doc = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "agent-run-auditor",
                        "version": __version__,
                        "informationUri": "https://github.com/mikkoatienza/agent-run-auditor",
                        "rules": rules,
                    }
                },
                "results": out,
            }
        ],
    }
    return json.dumps(doc, indent=2)


FORMATS = {"json": to_json, "md": to_markdown, "sarif": to_sarif}
