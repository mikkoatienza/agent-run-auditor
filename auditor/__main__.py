import sys
from .audit import load, audit

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: python -m auditor <run.jsonl> [...]")
    failed = False
    for path in sys.argv[1:]:
        print(f"== {path}")
        for f in audit(load(path)):
            failed |= not f.passed
            print(f"  {'PASS' if f.passed else 'FAIL'}  {f.check:24} {f.evidence}")
    sys.exit(1 if failed else 0)
