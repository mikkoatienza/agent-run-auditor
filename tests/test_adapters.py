from pathlib import Path

import pytest

from run_auditor.adapters import load_run, parse_chat, parse_jsonl, register_adapter
from run_auditor.models import Event


def test_jsonl_aliases_and_unknown_types() -> None:
    evs = parse_jsonl(
        '{"type": "command", "command": "ls", "exit_code": 0, "dur": 3}\n\n{"type": "weird"}'
    )
    assert evs[0].cmd == "ls" and evs[0].exit == 0 and evs[0].extra == {"dur": 3}
    assert evs[1].type == "message" and evs[1].extra["original_type"] == "weird"


def test_jsonl_error_has_line_number() -> None:
    with pytest.raises(ValueError, match="line 2"):
        parse_jsonl('{"type": "task"}\nnot json')


def test_chat_transcript(examples: Path) -> None:
    run = load_run(examples / "runs/chat-transcript.json")
    types = [e.type for e in run.events]
    assert types == ["task", "read", "edit", "edit", "command", "claim"]
    cmd = run.events[4]
    assert cmd.cmd == "pytest -q" and cmd.exit == 1 and cmd.output == "1 failed, 12 passed"
    assert [e.index for e in run.events] == list(range(6))


def test_chat_anthropic_style_blocks() -> None:
    evs = parse_chat(
        '[{"role": "user", "content": [{"type": "text", "text": "do it"}]},'
        '{"role": "assistant", "content": "", "tool_calls": ['
        '{"name": "bash", "input": {"cmd": "make"}}, {"name": "unknown_tool", "input": {}},'
        '{"name": "shell", "arguments": "echo raw"}]}]'
    )
    assert [(e.type, e.text or e.cmd) for e in evs] == [
        ("task", "do it"),
        ("command", "make"),
        ("command", "echo raw"),
    ]


def test_custom_adapter_and_errors(tmp_path: Path) -> None:
    @register_adapter("lines")
    def lines(text: str) -> list[Event]:
        return [Event("command", cmd=x) for x in text.splitlines()]

    p = tmp_path / "r.log"
    p.write_text("ls\npwd")
    assert [e.cmd for e in load_run(p, "lines").events] == ["ls", "pwd"]
    with pytest.raises(ValueError, match="unknown format"):
        load_run(p, "nope")
