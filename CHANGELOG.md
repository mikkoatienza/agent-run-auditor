# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-10-28
### Added
- First packaged release: `src/` layout, `pyproject.toml`, `agent-run-auditor` CLI.
- Pluggable interfaces with built-in offline implementations.
- Optional OpenAI / Anthropic adapters (extras `[openai]`, `[anthropic]`).
- YAML configuration, pytest suite, GitHub Actions CI (ruff, mypy, pytest).
