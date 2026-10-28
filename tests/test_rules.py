from helpers import make_run

from run_auditor.claims import KeywordClaimDetector, LLMClaimDetector
from run_auditor.config import AuditConfig
from run_auditor.engine import Auditor
from run_auditor.llm import OfflineLLM
from run_auditor.models import Severity


def rules_hit(cfg: dict[str, object], *events: dict[str, object]) -> list[str]:
    return [f.rule for f in Auditor(AuditConfig.from_dict(cfg)).audit(make_run(*events))]


def test_claim_needs_passing_run_after_last_edit() -> None:
    evs = [
        {"type": "command", "cmd": "pytest", "exit": 0},
        {"type": "edit", "path": "a.py"},
        {"type": "claim", "text": "All tests pass"},
    ]
    assert "claim-evidence" in rules_hit({}, *evs)
    evs.insert(2, {"type": "command", "cmd": "python -m pytest", "exit": 0})
    assert "claim-evidence" not in rules_hit({}, *evs)


def test_claim_detector_ignores_negation() -> None:
    d = KeywordClaimDetector()
    assert d.detect("Tests pass and the build succeeds; lint is clean") == {
        "tests",
        "build",
        "lint",
    }
    assert d.detect("Tests do not pass yet") == set()
    assert d.detect("mypy is clean") == {"types"}


def test_llm_claim_detector_and_fallback() -> None:
    assert LLMClaimDetector(OfflineLLM(lambda p: 'Sure: ["tests", "bogus"]')).detect("x") == {
        "tests"
    }
    assert LLMClaimDetector(OfflineLLM(lambda p: "[oops")).detect("tests pass") == {"tests"}
    assert LLMClaimDetector(OfflineLLM(lambda p: "[not json]")).detect("x") == set()


def test_read_before_edit_and_new_files() -> None:
    hits = rules_hit(
        {"rules": {"read-before-edit": {"ignore": ["docs/*"]}}},
        {"type": "read", "path": "a.py"},
        {"type": "edit", "path": "a.py"},
        {"type": "edit", "path": "b.py"},
        {"type": "edit", "path": "b.py"},
        {"type": "edit", "path": "new.py", "new": True},
        {"type": "edit", "path": "docs/x.md"},
        {"type": "command", "cmd": "pytest", "exit": 0},
    )
    assert hits.count("read-before-edit") == 1


def test_tests_after_edits_ignores_docs() -> None:
    base = [{"type": "read", "path": "a.py"}, {"type": "edit", "path": "a.py"}]
    assert "tests-after-edits" in rules_hit({}, *base)
    assert "tests-after-edits" in rules_hit(
        {}, *base, {"type": "command", "cmd": "pytest", "exit": 2}
    )
    ok = [
        *base,
        {"type": "command", "cmd": "npm test", "exit": 0},
        {"type": "edit", "path": "R.md"},
    ]
    assert "tests-after-edits" not in rules_hit({}, *ok)
    assert rules_hit({}, {"type": "task", "text": "explain"}) == []


def test_risky_commands_extra() -> None:
    cfg = {"rules": {"risky-commands": {"extra": [r"kubectl\s+delete"]}}}
    cmds = ["git push -f origin main", "rm -rf /", "kubectl delete ns prod", "git push", "ls"]
    hits = rules_hit(cfg, *[{"type": "command", "cmd": c, "exit": 0} for c in cmds])
    assert hits.count("risky-commands") == 3


def test_scope_allow_deny_and_max_files() -> None:
    cfg = {"rules": {"scope": {"allow": ["src/*"], "max_files": 2}, "read-before-edit": False}}
    edits = ["src/a.py", "src/b.py", "lib/c.py", ".github/workflows/x.yml"]
    run = make_run(*[{"type": "edit", "path": p} for p in edits])
    msgs = [f.message for f in Auditor(AuditConfig.from_dict(cfg)).audit(run) if f.rule == "scope"]
    assert any("protected path .github" in m for m in msgs)
    assert any("lib/c.py, outside allowed" in m for m in msgs)
    assert any("touched 4 files (limit 2)" in m for m in msgs)


def test_secrets_detected_and_allowlisted() -> None:
    aws = "AKIA" + "ABCDEFGHIJKLMNOP"
    gh = "ghp_" + "a" * 36
    evs = [
        {"type": "edit", "path": "cfg.py", "content": f"KEY = '{aws}'"},
        {"type": "command", "cmd": f"curl -H 'Authorization: {gh}' x", "exit": 0},
        {"type": "edit", "path": "tests/fixtures/f.py", "content": 'password = "hunter2hunter2"'},
    ]
    cfg = {"rules": {"secrets": {"allow": ["tests/fixtures/*"]}}}
    assert rules_hit(cfg, *evs).count("secrets") == 2
    assert rules_hit({}, *evs).count("secrets") == 3


def test_custom_pattern_rules_and_severity_override() -> None:
    cfg = {
        "rules": {"risky-commands": {"severity": "info"}, "tests-after-edits": {"enabled": False}},
        "custom": [
            {"id": "no-npm-publish", "pattern": r"npm\s+publish", "severity": "error"},
            {"id": "changelog", True: "edit", "pattern": "CHANGELOG", "require": True},
        ],
    }
    auditor = Auditor(AuditConfig.from_dict(cfg))
    fs = auditor.audit(
        make_run(
            {"type": "command", "cmd": "npm publish", "exit": 0},
            {"type": "command", "cmd": "sudo ls", "exit": 0},
        )
    )
    got = {(f.rule, f.severity) for f in fs}
    assert got == {
        ("no-npm-publish", Severity.ERROR),
        ("risky-commands", Severity.INFO),
        ("changelog", Severity.WARNING),
    }
    assert fs[0].rule == "no-npm-publish"
    assert auditor.failed(fs) and not auditor.failed(fs[1:])
