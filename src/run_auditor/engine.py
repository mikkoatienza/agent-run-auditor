"""Run configured rules over a run and collect findings."""

from __future__ import annotations

from .claims import ClaimDetector, KeywordClaimDetector, LLMClaimDetector
from .config import AuditConfig
from .llm import get_llm
from .models import Finding, Run, Severity
from .rules import REGISTRY, Context, RuleSpec, pattern_rule


class Auditor:
    """Applies built-in, plugin and custom rules according to an :class:`AuditConfig`."""

    def __init__(self, config: AuditConfig | None = None, claims: ClaimDetector | None = None):
        self.config = config or AuditConfig()
        if claims is None:
            claims = (
                LLMClaimDetector(get_llm())
                if self.config.claims == "llm"
                else KeywordClaimDetector()
            )
        self.context = Context(claims=claims)

    def rules(self) -> list[RuleSpec]:
        """Active rules: registry plus custom pattern rules, minus disabled ones."""
        specs = list(REGISTRY.values()) + [pattern_rule(c) for c in self.config.custom]
        unknown = set(self.config.rules) - {s.id for s in specs}
        if unknown:
            raise ValueError(f"config references unknown rules: {sorted(unknown)}")
        return [
            s
            for s in specs
            if self.config.rules.get(s.id) is None or self.config.rules[s.id].enabled
        ]

    def audit(self, run: Run) -> list[Finding]:
        """Return all findings for ``run``, most severe first, then in log order."""
        findings = []
        for spec in self.rules():
            rc = self.config.rules.get(spec.id)
            severity = (rc.severity if rc else None) or spec.severity
            for hit in spec.fn(run, rc.options if rc else {}, self.context):
                findings.append(
                    Finding(
                        rule=spec.id,
                        severity=severity,
                        message=hit.message,
                        event_index=hit.event.index if hit.event else None,
                        path=hit.path,
                        source=run.source,
                    )
                )
        findings.sort(
            key=lambda f: (-f.severity, f.event_index if f.event_index is not None else -1)
        )
        return findings

    def failed(self, findings: list[Finding], fail_on: Severity | None = None) -> bool:
        """True when any finding meets the failure threshold."""
        threshold = fail_on or self.config.fail_on
        return any(f.severity >= threshold for f in findings)
