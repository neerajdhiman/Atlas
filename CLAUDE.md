# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Backend (Python)
```bash
# Install (editable, from project root)
.venv/Scripts/python -m pip install -e .           # core
.venv/Scripts/python -m pip install -e ".[dev]"     # + pytest, ruff, pytest-cov
.venv/Scripts/python -m pip install -e ".[training]" # + unsloth, datasets, lm-eval

# Run backend
.venv/Scripts/python -m uvicorn src.a1.app:app --host 0.0.0.0 --port 8000 --reload

# Tests
.venv/Scripts/python -m pytest tests/ -v
.venv/Scripts/python -m pytest tests/ --cov=src/a1

# Lint
ruff check src/ tests/
ruff format src/ tests/
```

### Dashboard (React + Vite)
```bash
cd dashboard-ui
npm install
npm run dev       # :5173 with HMR
npm run build     # production build → dist/
```

### Database Migrations
```bash
alembic upgrade head                          # apply all
alembic revision --autogenerate -m "message"  # new migration
alembic downgrade -1                          # rollback one
```

### Docker (infrastructure only)
```bash
docker compose up -d                          # postgres + redis
docker compose --profile feedback up -d       # + argilla
docker compose --profile observability up -d  # + jaeger
```

## Architecture

A1 Trainer is an OpenAI-compatible LLM proxy that routes requests to local Ollama servers (preferred, free) or external providers (Claude, GPT, Gemini via LiteLLM). The unified model name **alpheric-1** auto-routes to the best available local model.

### Request flow
`POST /v1/chat/completions` → `proxy/router.py` → classify task type → select model via `routing/strategy.py` → check GPTCache → call provider → track tokens/cost → persist to DB → return response with `X-A1-*` headers.

When `model=alpheric-1`, it rewrites to `auto` and uses `best_quality` strategy. When `model=auto`, the classifier in `routing/classifier.py` determines task type (code, chat, math, etc.) and `routing/strategy.py` picks the best model from `config/routing_policy.yaml` cold-start defaults.

### Provider abstraction
All providers inherit from `providers/base.py:LLMProvider` (abstract methods: `complete`, `stream`, `health_check`, `supports_model`, `list_models`). The singleton `providers/registry.py:provider_registry` initializes providers at startup and maintains health state. To add a new provider: create a file in `providers/`, inherit `LLMProvider`, register it in `ProviderRegistry.initialize()`.

### Key singletons
- `provider_registry` (`providers/registry.py`) — all provider instances + health
- `metrics` (`common/metrics.py`) — in-memory request/latency/cost counters
- `settings` (`config/settings.py`) — Pydantic BaseSettings, all env vars prefixed `A1_`

### Database
SQLAlchemy async with 10 ORM models in `db/models.py`. Dev uses SQLite (`a1_trainer.db`), prod uses PostgreSQL. The `db/repositories.py` module provides typed query helpers (ConversationRepo, MessageRepo, RoutingRepo, etc.).

### Dashboard API
`dashboard/router.py` exposes 25+ endpoints under `/admin/*` including a WebSocket live feed at `/admin/ws/live-feed`. The React frontend in `dashboard-ui/` connects to these and renders 10 pages.

### Multi-server Ollama
`providers/ollama.py` discovers models from all servers in `settings.ollama_servers` via `/api/tags`, maps each model to its server, and routes requests to the correct server. Currently: 10.0.0.9 (code models) and 10.0.0.10 (QA/reasoning models).

## Configuration

All settings are in `config/settings.py` with `A1_` env prefix, loaded from `.env`. Key groups:
- **Database**: `A1_DATABASE_URL` (SQLite for dev, PostgreSQL for prod)
- **Ollama**: `A1_OLLAMA_SERVERS` (JSON array of server URLs)
- **OpenClaw**: `A1_OPENCLAW_URL`, `A1_OPENCLAW_TOKEN`
- **Feature flags**: `A1_USE_LITELLM`, `A1_CACHE_ENABLED`, `A1_USE_UNSLOTH`, `A1_USE_HARNESS_EVAL`
- **Provider keys**: `A1_ANTHROPIC_API_KEY`, `A1_OPENAI_API_KEY`, `A1_VERTEX_PROJECT_ID`

Provider model definitions live in `config/providers.yaml`. Task-to-model routing defaults live in `config/routing_policy.yaml`.

## Conventions

- Backend async everywhere — all DB calls use `async with session`, all HTTP via `httpx.AsyncClient`
- Tests use `pytest-asyncio` with `asyncio_mode = "auto"`
- Ruff for linting: line-length 100, target Python 3.11
- Dashboard uses Ant Design components, Zustand stores, Axios API client in `dashboard-ui/src/lib/api.ts`
- Response headers `X-A1-Provider`, `X-A1-Is-Local`, `X-A1-Cost`, `X-A1-Tokens-In`, `X-A1-Tokens-Out`, `X-A1-Cache` are added to every proxy response
