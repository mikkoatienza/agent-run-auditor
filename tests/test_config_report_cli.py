import json
from pathlib import Path

import pytest

from run_auditor.cli import main
from run_auditor.config import SAMPLE, AuditConfig
from run_auditor.engine import Auditor
from run_auditor.models import Severity
from run_auditor.rules import REGISTRY


def test_config_validation(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown config keys"):
        AuditConfig.from_dict({"bogus": 1})
    with pytest.raises(ValueError, match="unknown severity"):
        AuditConfig.from_dict({"fail_on": "fatal"})
    with pytest.raises(ValueError, match="unknown rules"):
        Auditor(AuditConfig.from_dict({"rules": {"nope": {}}})).rules()
    p = tmp_path / "a.yaml"
    p.write_text(SAMPLE)
    cfg = AuditConfig.load(p)
    assert cfg.rules["scope"].options["max_files"] == 10
    assert any(s.id == "changelog-updated" for s in Auditor(cfg).rules())
    assert AuditConfig.load(None).fail_on is Severity.ERROR


def test_plugin_loading(examples: Path) -> None:
    AuditConfig.load(examples / "auditor.yaml")
    assert "no-new-todos" in REGISTRY


def test_llm_claims_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "offline")
    from run_auditor.claims import LLMClaimDetector

    assert isinstance(Auditor(AuditConfig(claims="llm")).context.claims, LLMClaimDetector)


def test_cli_exit_codes_and_formats(
    examples: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cfg = ["-c", str(examples / "auditor.yaml")]
    good, bad = str(examples / "runs/good-run.jsonl"), str(examples / "runs/bad-run.jsonl")
    assert main(["audit", good, *cfg]) == 0
    assert "clean" in capsys.readouterr().out
    assert main(["audit", bad, *cfg]) == 1
    assert main(["audit", bad, *cfg, "--fail-on", "never"]) == 0
    assert main(["audit", good]) == 0  # default config has no changelog rule
    capsys.readouterr()

    assert main(["audit", bad, good, *cfg, "-f", "json", "--fail-on", "never"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["summary"]["error"] == 5 and doc["runs"][good] == []

    out = tmp_path / "a.sarif"
    assert main(["audit", bad, *cfg, "-f", "sarif", "-o", str(out)]) == 1
    sarif = json.loads(out.read_text())
    assert sarif["version"] == "2.1.0"
    results = sarif["runs"][0]["results"]
    levels = {r["level"] for r in results}
    assert levels == {"error", "warning", "note"}
    risky = next(r for r in results if r["ruleId"] == "risky-commands")
    assert risky["locations"][0]["physicalLocation"]["region"]["startLine"] == 6

    assert main(["audit", bad, *cfg, "-f", "md", "--fail-on", "warning"]) == 1
    assert "## Agent run audit" in capsys.readouterr().out


def test_cli_rules_init_and_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["rules"]) == 0
    assert "claim-evidence" in capsys.readouterr().out
    p = tmp_path / "auditor.yaml"
    assert main(["init", str(p)]) == 0 and main(["init", str(p)]) == 1
    assert main(["audit", str(tmp_path / "missing.jsonl")]) == 2
