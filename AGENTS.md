# Repository Guidelines

## Project Structure & Module Organization

```
src/clawhermes/
├── agent/       # Agent loop, memory, sessions, scheduler, pairing
├── channel/     # ChannelAdapter SDK, adapters (feishu/wechat/qq), router
├── gateway/     # FastAPI HTTP API (33 endpoints)
├── llm/         # LLM provider abstraction (litellm)
├── mcp/         # MCP client for tool servers
├── skills/      # Skill Hub — curated agent skills
├── storage/     # ChromaDB / JSON persistence
└── tools/       # Built-in tools (35 registered)

tests/           # pytest (416 cases), mirror src/ structure
config/          # Config examples: .env.example, config.yaml.example, channels/
docs/            # Architecture, API contract, development plan, env reference
scripts/         # install.sh (one-line bootstrap)
clawhermes-*/    # Channel submodules (lark, weixin, qq) — pip install -e ./clawhermes-*
```

## Build, Test, and Development Commands

```bash
pip install -e ".[dev]"          # install with dev deps (pytest, ruff, mypy)
ruff check src/                  # lint — rules: E, F, I, N, W (100-char line limit)
mypy src/                        # type check — Python 3.12, warn_return_any
pytest -q                        # run all 416 tests (~23s)
pytest tests/test_cli.py -x      # run single test file, stop on first failure
python -m clawhermes.cli setup   # interactive config wizard
python -m clawhermes.cli gateway start  # start Gateway on :18789
```

## Coding Style & Naming Conventions

- **Formatter**: Ruff (line length 100, `pyproject.toml`)
- **Type hints**: All public functions annotated; mypy `warn_return_any` enforced
- **Imports**: `from __future__ import annotations` in every file; isort via ruff I001
- **Naming**: `snake_case` for functions/vars, `PascalCase` for classes/dataclasses
- **Channel adapters**: Adapter classes in `src/clawhermes/channel/adapters/`, SDK in submodules

## Testing Guidelines

- **Framework**: pytest + pytest-asyncio + pytest-cov
- **Coverage**: `--cov-fail-under=60` on `src/clawhermes/` (soft gate via `|| true`)
- **File naming**: `test_<module>.py`, one-to-one with source modules
- **Mock strategy**: `MockProvider` in `tests/mock_provider.py`; channel tests auto-skip if submodule missing
- Run with: `pytest --tb=short -q`

## Commit & Pull Request Guidelines

- **Format**: Conventional commits — `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`, `style:`
- **Branch naming**: `feature/<name>`, `fix/<name>`, `bugfix/<name>` — semantic, kebab-case
- **PR requirements**: One feature per PR, CI must pass (lint + typecheck + test), squash merge
- **Submodule changes**: Commit in submodule first, then update pointer in main repo
- **Config changes**: `.env` for secrets only; operational config in `channels/*.yaml` with `${VAR}` interpolation
