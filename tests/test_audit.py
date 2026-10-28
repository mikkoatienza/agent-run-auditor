import unittest
from auditor.audit import load, audit

def by_name(path):
    return {f.check: f.passed for f in audit(load(path))}

class AuditTest(unittest.TestCase):
    def test_good_run_passes_everything(self):
        self.assertTrue(all(by_name("samples/good-run.jsonl").values()))

    def test_bad_run_flags_each_problem(self):
        r = by_name("samples/bad-run.jsonl")
        for check in ("read-before-edit", "tests-pass-after-edits",
                      "claims-match-evidence", "no-risky-commands", "scope"):
            self.assertFalse(r[check], check)

if __name__ == "__main__":
    unittest.main()
