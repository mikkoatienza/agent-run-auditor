# agent-run-auditor

[![CI](https://github.com/mikkoatienza/agent-run-auditor/actions/workflows/ci.yml/badge.svg)](https://github.com/mikkoatienza/agent-run-auditor/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%2B-blue) ![License: MIT](https://img.shields.io/badge/license-MIT-green)

**Check what a coding agent _did_, not what it _says_ it did.**

Feed in the run log of any coding agent: the files it read and edited, the commands it ran with their exit codes, and its final message. The auditor applies evidence-based rules and produces findings as text, Markdown, JSON or **SARIF**. You can use it as a CI gate, a PR comment, or a code-scanning alert.

```text
== bad-run.jsonl: 10 finding(s)
  ERROR   secrets            #3   possible hard-coded credential in edit content
  ERROR   tests-after-edits  #4   no passing test run after the last edit (.github/workflows/ci.yml)
  ERROR   risky-commands     #5   risky command: git push --force origin main
  ERROR   claim-evidence     #6   claims tests succeeded but no matching command ran after the last edit
  WARNING read-before-edit   #1   edited src/pager.py without reading it first
  ...
```

## Built-in rules
| Rule | Default | Fires when |
|---|---|---|
| `claim-evidence` | error | The agent claims tests, build, lint or type checks pass, but no matching command exited 0 after the last edit before the claim |
| `tests-after-edits` | error | No passing test run follows the last code edit (docs are ignored) |
| `risky-commands` | error | `push --force`, `rm -rf /`, `reset --hard`, `--no-verify`, `DROP TABLE`, `curl \| sh`, `sudo`… plus your own patterns |
| `secrets` | error | AWS/GitHub/Slack/OpenAI-style keys, private keys or hard-coded credentials appear in edits, commands or output |
| `read-before-edit` | warning | An existing file is edited without being read first |
| `scope` | warning | Edits fall outside `allow` globs, touch `deny` globs (CI config, lockfiles), or exceed `max_files` |

You can change any rule's severity, disable it, or tune its options in YAML. You can also add your own rules, either as YAML pattern rules or as Python plugins.

## Quickstart
```bash
pip install "git+https://github.com/mikkoatienza/agent-run-auditor"
agent-run-auditor init                       # writes auditor.yaml
agent-run-auditor audit run.jsonl -c auditor.yaml
agent-run-auditor audit run.jsonl -f sarif -o audit.sarif
agent-run-auditor audit runs/*.jsonl -f md --fail-on warning >> "$GITHUB_STEP_SUMMARY"
agent-run-auditor rules                      # list active rules
```
Exit codes: `0` means no findings at or above `fail_on`, `1` means some were found, and `2` means an input or config error.

Try it with the bundled examples:
```bash
pip install -e ".[dev]"
python examples/run_demo.py
agent-run-auditor audit examples/runs/*.json* -c examples/auditor.yaml
```

## Log formats
**Native JSONL**, with one event per line:
```json
{"type": "task", "text": "Fix the off-by-one in src/pager.py"}
{"type": "read", "path": "src/pager.py"}
{"type": "edit", "path": "src/pager.py", "content": "..."}
{"type": "edit", "path": "tests/test_pager.py", "new": true}
{"type": "command", "cmd": "pytest", "exit": 0, "output": "..."}
{"type": "claim", "text": "Fixed; all tests pass."}
```
**Chat transcript JSON** (`--input-format chat`, which is the default for `.json`): `messages` with `tool_calls` in OpenAI or Anthropic style, plus `tool` results that carry an `exit_code`. Tool names such as `read_file`, `edit_file`, `str_replace`, `bash` and `shell` are mapped to events through `adapters.TOOL_MAP`. You can extend that map.

For any other format, write an adapter:
```python
from run_auditor.adapters import register_adapter
from run_auditor.models import Event


@register_adapter("mylog")
def parse(text: str) -> list[Event]: ...
```

## Architecture
```mermaid
flowchart LR
    L1[run.jsonl] --> A[Adapters<br/>jsonl / chat / custom]
    L2[chat transcript] --> A
    A --> R[Run<br/>normalized events]
    C[auditor.yaml] --> E[Auditor]
    P[plugins/*.py<br/>@rule] --> REG[Rule registry]
    B[Built-in rules] --> REG
    C -- custom pattern rules --> E
    REG --> E
    R --> E
    CD[ClaimDetector<br/>keyword or LLM] --> E
    E --> F[Findings + severity]
    F --> O1[text]
    F --> O2[Markdown]
    F --> O3[JSON]
    F --> O4[SARIF 2.1.0]
    F --> G{fail_on gate}
```

## Configuration
```yaml
fail_on: error            # info | warning | error
claims: keyword           # keyword | llm  (LLM_PROVIDER=offline|openai|anthropic)
rules:
  read-before-edit: {ignore: ["tests/*"]}
  risky-commands: {extra: ["kubectl\\s+delete"], severity: error}
  scope: {allow: ["src/*", "tests/*"], max_files: 10}
  secrets: {allow: ["tests/fixtures/*"]}
  tests-after-edits: {test_command: "make check"}
  claim-evidence:
    evidence_commands: {tests: "make check"}
custom:
  - id: changelog-updated
    event: edit
    pattern: "CHANGELOG\\.md$"
    require: true          # fire when NO event matches
    severity: info
    message: CHANGELOG.md was not updated
plugins:
  - plugins/no_todo.py     # path relative to this file, or an importable module
```

## Writing a rule in Python
```python
from run_auditor.models import Run, Severity
from run_auditor.rules import Context, Hit, rule


@rule("no-new-todos", Severity.INFO, "Edits should not add TODO/FIXME markers")
def no_new_todos(run: Run, opts: dict, ctx: Context) -> list[Hit]:
    return [
        Hit(f"{e.path} adds a TODO", e, e.path)
        for e in run.of("edit")
        if e.content and "TODO" in e.content
    ]
```
See [`examples/plugins/no_todo.py`](examples/plugins/no_todo.py).

## Claim detection
`KeywordClaimDetector` is the default. It is regex-based and deterministic, and it ignores negated statements such as "tests don't pass yet". Set `claims: llm` to have an LLM classify messages instead (`pip install ".[openai]"` or `".[anthropic]"`, then set `LLM_PROVIDER` and the API key). If the model's answer can't be parsed, the auditor falls back to keywords. `LLM_PROVIDER=offline` gives a deterministic stub for tests.

## GitHub Actions
[`examples/github-action.yml`](examples/github-action.yml) shows a workflow that downloads an agent's run log artifact, writes a Markdown job summary, and uploads SARIF to code scanning. The job fails on errors.

## Roadmap
- Adapters for more agent frameworks' native trace formats
- Diff-aware rules, for example "test files changed only to weaken assertions"
- Baselines and suppressions (`# auditor: ignore[rule]`)
- Publishing as a reusable composite GitHub Action
- An HTML report with an event timeline

## Development
```bash
pip install -e ".[dev]"
ruff check . && ruff format --check . && mypy && pytest
```
See [CONTRIBUTING.md](CONTRIBUTING.md) and [CHANGELOG.md](CHANGELOG.md).

## License
MIT © Mikko Atienza
