"""Audit the three example runs and print a Markdown report.

python examples/run_demo.py
"""

from __future__ import annotations

from pathlib import Path

from run_auditor.adapters import load_run
from run_auditor.config import AuditConfig
from run_auditor.engine import Auditor
from run_auditor.report import to_markdown

HERE = Path(__file__).parent


def main() -> None:
    auditor = Auditor(AuditConfig.load(HERE / "auditor.yaml"))
    results = {}
    for log in sorted((HERE / "runs").iterdir()):
        results[log.name] = auditor.audit(load_run(log))
    print(to_markdown(results))
    for name, findings in results.items():
        print(f"{name}: {'FAIL' if auditor.failed(findings) else 'pass'}")


if __name__ == "__main__":
    main()
