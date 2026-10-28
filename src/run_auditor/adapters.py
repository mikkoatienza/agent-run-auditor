"""Adapters that turn agent logs into a normalized :class:`~run_auditor.models.Run`.

Two formats ship built in:

* ``jsonl`` - the native format, one event object per line
  (``{"type": "edit", "path": "app.py"}``).
* ``chat`` - a generic chat transcript with tool calls, in the shape most agent SDKs log:
  ``{"messages": [{"role": "assistant", "content": "...", "tool_calls": [...]},
  {"role": "tool", "tool_call_id": "...", "content": "...", "exit_code": 0}]}``.

Register your own with :func:`register_adapter`.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .models import EVENT_TYPES, Event, Run

Adapter = Callable[[str], list[Event]]
ADAPTERS: dict[str, Adapter] = {}

#: Tool names (lower-case) mapped to event types for the chat adapter.
TOOL_MAP: dict[str, str] = {
    "read_file": "read",
    "read": "read",
    "view": "read",
    "open_file": "read",
    "cat": "read",
    "write_file": "edit",
    "edit_file": "edit",
    "edit": "edit",
    "write": "edit",
    "apply_patch": "edit",
    "str_replace": "edit",
    "create_file": "edit",
    "bash": "command",
    "shell": "command",
    "run_command": "command",
    "exec": "command",
    "terminal": "command",
}


def register_adapter(name: str) -> Callable[[Adapter], Adapter]:
    """Decorator registering a ``text -> list[Event]`` adapter under ``name``."""

    def deco(fn: Adapter) -> Adapter:
        ADAPTERS[name] = fn
        return fn

    return deco


def _event(d: dict[str, Any]) -> Event:
    known = {k: d[k] for k in ("path", "content", "cmd", "exit", "output", "text", "ts") if k in d}
    if "command" in d and "cmd" not in known:
        known["cmd"] = d["command"]
    if "exit_code" in d and "exit" not in known:
        known["exit"] = d["exit_code"]
    extra = {
        k: v for k, v in d.items() if k not in known and k not in ("type", "command", "exit_code")
    }
    etype = str(d.get("type", "message"))
    if etype not in EVENT_TYPES:
        extra["original_type"] = etype
        etype = "message"
    return Event(type=etype, extra=extra, **known)


@register_adapter("jsonl")
def parse_jsonl(text: str) -> list[Event]:
    """Parse the native one-event-per-line format."""
    events = []
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"line {n}: invalid JSON ({exc.msg})") from None
        events.append(_event(d))
    return events


def _args(call: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    fn = call.get("function", call)
    name = str(fn.get("name", "")).lower()
    raw = fn.get("arguments", fn.get("input", {}))
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {"command": raw}
    return name, raw if isinstance(raw, dict) else {}


@register_adapter("chat")
def parse_chat(text: str) -> list[Event]:
    """Parse a chat transcript with tool calls (see module docstring)."""
    data = json.loads(text)
    messages = data["messages"] if isinstance(data, dict) else data
    events: list[Event] = []
    pending: dict[str, Event] = {}
    first_user = True
    for m in messages:
        role = m.get("role")
        content = m.get("content") or ""
        if isinstance(content, list):
            content = " ".join(str(p.get("text", "")) for p in content if isinstance(p, dict))
        if role == "user" and first_user:
            events.append(Event("task", text=content))
            first_user = False
        elif role == "assistant":
            if content.strip():
                events.append(Event("claim", text=content))
            for call in m.get("tool_calls") or []:
                name, args = _args(call)
                etype = TOOL_MAP.get(name)
                if etype is None:
                    continue
                path = args.get("path") or args.get("file") or args.get("file_path")
                ev = Event(
                    etype,
                    path=path,
                    cmd=args.get("command") or args.get("cmd"),
                    content=args.get("content") or args.get("new_str") or args.get("patch"),
                )
                events.append(ev)
                if call.get("id"):
                    pending[str(call["id"])] = ev
        elif role == "tool":
            result = pending.get(str(m.get("tool_call_id")))
            if result is not None and result.type == "command":
                result.output = content
                code = m.get("exit_code", m.get("exit"))
                result.exit = int(code) if code is not None else None
    return events


def load_run(path: str | Path, fmt: str | None = None) -> Run:
    """Load a run log, picking the adapter from ``fmt`` or the file extension."""
    p = Path(path)
    if fmt is None:
        fmt = "chat" if p.suffix == ".json" else "jsonl"
    if fmt not in ADAPTERS:
        raise ValueError(f"unknown format {fmt!r}; available: {', '.join(sorted(ADAPTERS))}")
    events = ADAPTERS[fmt](p.read_text(encoding="utf-8"))
    for i, e in enumerate(events):
        e.index = i
    return Run(events, source=str(p))
