"""Command-line interface: ``agent-run-auditor audit|rules|init``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .adapters import ADAPTERS, load_run
from .config import SAMPLE, AuditConfig
from .engine import Auditor
from .models import Finding, Severity
from .report import FORMATS


def _text(results: dict[str, list[Finding]]) -> str:
    lines = []
    for src, fs in results.items():
        lines.append(f"== {src}: {'clean' if not fs else f'{len(fs)} finding(s)'}")
        for f in fs:
            ev = "" if f.event_index is None else f"#{f.event_index:<3}"
            lines.append(f"  {str(f.severity).upper():7} {f.rule:18} {ev:4} {f.message}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    ap = argparse.ArgumentParser(prog="agent-run-auditor", description=__doc__)
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("audit", help="audit one or more run logs")
    a.add_argument("logs", nargs="+", type=Path)
    a.add_argument("-c", "--config", type=Path)
    a.add_argument("--input-format", choices=sorted(ADAPTERS), help="default: by extension")
    a.add_argument("-f", "--format", choices=["text", *FORMATS], default="text")
    a.add_argument("-o", "--output", type=Path, help="write the report here (stdout if omitted)")
    a.add_argument("--fail-on", choices=["info", "warning", "error", "never"])

    sub.add_parser("rules", help="list available rules")
    i = sub.add_parser("init", help="write a sample auditor.yaml")
    i.add_argument("path", nargs="?", type=Path, default=Path("auditor.yaml"))
    return ap


def main(argv: list[str] | None = None) -> int:
    """Entry point. Exit codes: 0 ok, 1 findings at/above threshold, 2 usage/input error."""
    args = build_parser().parse_args(argv)
    if args.cmd == "init":
        if args.path.exists():
            print(f"{args.path} already exists", file=sys.stderr)
            return 1
        args.path.write_text(SAMPLE)
        print(f"wrote {args.path}")
        return 0
    try:
        auditor = Auditor(AuditConfig.load(getattr(args, "config", None)))
        if args.cmd == "rules":
            for spec in auditor.rules():
                print(f"{spec.id:20} {str(spec.severity):8} {spec.description}")
            return 0
        results = {str(p): auditor.audit(load_run(p, args.input_format)) for p in args.logs}
    except (OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    report = _text(results) if args.format == "text" else FORMATS[args.format](results)
    if args.output:
        args.output.write_text(report + "\n")
        print(f"wrote {args.output}")
    else:
        print(report)
    if args.fail_on == "never":
        return 0
    threshold = Severity.parse(args.fail_on) if args.fail_on else None
    all_f = [f for fs in results.values() for f in fs]
    return 1 if auditor.failed(all_f, threshold) else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
