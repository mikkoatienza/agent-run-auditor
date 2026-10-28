# agent-run-auditor

Audit a coding agent's run log against **evidence, not claims**.

Agents often say "fixed, all tests pass." This tool reads the run log (JSON Lines) and checks what actually happened:

| Check | Fails when |
|---|---|
| `read-before-edit` | a source file was edited without being read first |
| `tests-pass-after-edits` | there is no passing test run after the last edit |
| `claims-match-evidence` | the agent claims tests pass but the last test run failed |
| `no-risky-commands` | force-push, `reset --hard`, `--no-verify`, etc. |
| `scope` | edits touch files unrelated to the task |

## Quick start
```bash
python -m auditor samples/good-run.jsonl   # all PASS, exit 0
python -m auditor samples/bad-run.jsonl    # each check FAILs, exit 1
python -m unittest -v
```
Requires Python 3.10+. No dependencies. The non-zero exit code makes it easy to use as a CI gate.

## Log format
One JSON object per line: `task {text}`, `read {path}`, `edit {path}`, `command {cmd, exit}`, `claim {text}`. Write a small adapter to convert your agent tool's transcript into this format.

## License
MIT
