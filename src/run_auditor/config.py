"""YAML configuration for rules, custom pattern rules and plugins."""

from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .models import Severity

KEYS = {"fail_on", "rules", "custom", "plugins", "claims"}


@dataclass
class RuleConfig:
    """Per-rule settings."""

    enabled: bool = True
    severity: Severity | None = None
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class AuditConfig:
    """Top-level auditor configuration (see ``SAMPLE``)."""

    fail_on: Severity = Severity.ERROR
    rules: dict[str, RuleConfig] = field(default_factory=dict)
    custom: list[dict[str, Any]] = field(default_factory=list)
    plugins: list[str] = field(default_factory=list)
    claims: str = "keyword"

    @classmethod
    def from_dict(cls, data: dict[str, Any], base: Path | None = None) -> AuditConfig:
        """Build from parsed YAML; unknown keys raise ``ValueError``."""
        unknown = set(data) - KEYS
        if unknown:
            raise ValueError(f"unknown config keys: {sorted(unknown)}")
        rules = {}
        for rid, raw in (data.get("rules") or {}).items():
            if isinstance(raw, bool):
                rules[rid] = RuleConfig(enabled=raw)
                continue
            raw = dict(raw or {})
            sev = raw.pop("severity", None)
            enabled = bool(raw.pop("enabled", True))
            rules[rid] = RuleConfig(enabled, Severity.parse(sev) if sev else None, raw)
        cfg = cls(
            fail_on=Severity.parse(data.get("fail_on", "error")),
            rules=rules,
            custom=list(data.get("custom") or []),
            plugins=list(data.get("plugins") or []),
            claims=str(data.get("claims", "keyword")),
        )
        cfg.load_plugins(base)
        return cfg

    @classmethod
    def load(cls, path: str | Path | None) -> AuditConfig:
        """Load YAML from ``path``; ``None`` gives defaults."""
        if path is None:
            return cls()
        p = Path(path)
        return cls.from_dict(yaml.safe_load(p.read_text()) or {}, p.parent)

    def load_plugins(self, base: Path | None) -> None:
        """Import plugin modules so their ``@rule`` decorators register.

        Entries are module names (``my_rules``) or paths relative to the config
        (``plugins/my_rules.py``).
        """
        for name in self.plugins:
            if name.endswith(".py"):
                path = (base or Path.cwd()) / name
                sys.path.insert(0, str(path.parent))
                name = path.stem
            importlib.import_module(name)


SAMPLE = """\
# agent-run-auditor configuration
fail_on: error            # exit non-zero when a finding is at least this severe
claims: keyword           # keyword | llm  (llm uses LLM_PROVIDER: offline|openai|anthropic)

rules:
  claim-evidence: {}
  read-before-edit:
    ignore: ["tests/*"]
  tests-after-edits:
    ignore: ["*.md", "docs/*"]
  risky-commands:
    extra: ["kubectl\\\\s+delete"]
  scope:
    allow: ["src/*", "tests/*"]
    max_files: 10
  secrets:
    allow: ["tests/fixtures/*"]

# Pattern rules without writing Python:
custom:
  - id: changelog-updated
    event: edit
    pattern: "CHANGELOG\\\\.md$"
    require: true
    severity: info
    message: CHANGELOG.md was not updated

# Python rule modules (use @rule from run_auditor.rules):
plugins: []
"""
