# Contributing

Thanks for helping improve ****.

## Setup
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Before opening a PR
```bash
ruff check . && ruff format --check . && mypy && pytest
```
CI runs the same commands on Python 3.10 and 3.12.

## Guidelines
- Keep the core dependency-light. Provider SDKs stay optional extras.
- New behaviour goes behind an interface (see the extension guide in the README) with a test.
- Tests must run offline. Use the deterministic offline providers, never real API keys.
- Keep public functions typed and documented.
