# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Backend (Python)
```bash
# Install (editable, from project root)
.venv/Scripts/python -m pip install -e .           # core
.venv/Scripts/python -m pip install -e ".[dev]"     # + pytest, ruff, pytest-cov
.venv/Scripts/python -m pip install -e ".[training]" # + unsloth, datasets, lm-eval

# Run backend (MUST set PYTHONIOENCODING for Claude CLI emoji handling on Windows)
PYTHONIOENCODING=utf-8 .venv/Scripts/python -m uvicorn src.a1.app:app --host 0.0.0.0 --port 8001

# Tests
.venv/Scripts/python -m pytest tests/ -v

# Lint
ruff check src/ tests/
ruff format src/ tests/
```

### Dashboard (React + Vite)
```bash
cd dashboard-ui
npm install
npm run dev       # :5173 with HMR — proxies to http://localhost:8001
npm run build     # production build → dist/
```
The Vite proxy config in `dashboard-ui/vite.config.ts` must match the backend port (currently 8001).

### Database Migrations
```bash
alembic upgrade head                          # apply all pending migrations
alembic downgrade base                        # roll back everything (dev only)
alembic revision --autogenerate -m "message"  # generate a new migration from model diff
alembic history                               # show migration chain
alembic current                               # show current DB revision
```

**Migration chain:** `0000_initial_schema` → `0001_add_max_local_pct` → …

**Adding a new migration:**
1. Edit `src/a1/db/models.py` to add/change columns.
2. Run `alembic revision --autogenerate -m "describe_the_change"`.
3. Review the generated file in `alembic/versions/` — autogenerate is not always perfect.
4. Run `alembic upgrade head` to apply.

**Production note:** Never use `create_all` directly against a prod DB. Always go through migrations.

## Architecture

**Alpheric.AI** is an enterprise AI middleware with the **Atlas** model family. It routes requests through Claude Opus (via CLI proxy) as the "teacher", streams responses to users in real-time, and trains local Ollama models in the background to eventually handle requests independently.

### Product: Alpheric.AI / Atlas Model Family
- 7 Atlas models: `atlas-plan` (chat), `atlas-code` (code), `atlas-secure` (security), `atlas-infra` (devops), `atlas-data` (analytics), `atlas-books` (writing), `atlas-audit` (compliance)
- Legacy alias `alpheric-1` maps to `atlas-plan`
- Each model maps to a task type and preferred local fallback model

### Request Flow
Three entry points, all in `proxy/router.py`:

1. **`POST /atlas`** — Primary endpoint. Auto-selects Atlas model from content classification, or accepts explicit model. Supports `stream:true` for SSE.
2. **`POST /v1/responses`** — OpenAI Responses API format (used by OpenClaw). Maps `instructions` + `tools` + `input` to messages.
3. **`POST /v1/chat/completions`** — Standard OpenAI-compatible endpoint.

All three follow the same pipeline:
```
Request → Session Memory (load history) → PII Masking → Task Classification
  → Atlas Model Resolution → Claude CLI (distillation) or Local Ollama
  → PII Unmask Response → Store in Session → Persist to DB → Return (JSON or SSE stream)
```

### Distillation Pipeline (`training/auto_trainer.py`)
When `A1_DISTILLATION_ENABLED=true` (default), ALL Atlas model requests go to Claude Opus via CLI:
1. Claude responds (teacher) — returned to user immediately
2. Background: same request sent to best local Ollama model (student)
3. Responses compared (Jaccard similarity)
4. Stored in `DualExecutionRecord` table
5. When 100+ samples accumulate per task type → auto-triggers QLoRA training
6. After successful training → graduated handoff % increases (0% → 90% max)

### Claude CLI Provider (`providers/claude_cli.py`)
Proxies requests through the local `claude` command. Key details:
- Uses `--output-format json` for accurate token counts and cost
- Uses `--system-prompt` to inject Atlas identity ("You are Atlas by Alpheric.AI")
- True streaming via stdout pipe reading (80-byte chunks)
- **Windows requires `PYTHONIOENCODING=utf-8`** at process level or emojis in Claude's responses crash the cp1252 codec
- Falls back to `llama3.2:latest` if Claude CLI fails

### Session Memory (`session/manager.py`)
In-memory LRU cache (1000 sessions, 1hr TTL). Sessions are resolved by:
1. Explicit `session_id` in request
2. `previous_response_id` → looks up which session produced that response
3. Neither → creates new session

Session history (last 20 messages) is prepended to messages before sending to Claude.

### PII Masking (`security/pii_masker.py`)
Detects and masks sensitive data (email, phone, SSN, credit card, API keys, IPs) before external API calls. Maintains a reversible `mask_map` so responses are unmasked for the user. Only applied for external providers (`pii_mask_for_external_only=true`).

### SSE Streaming (`proxy/stream.py`)
Two streaming formats:
- `sse_stream()` — OpenAI chat completion chunks (`data: {...}\n\n`)
- `sse_responses_stream_live()` — OpenAI Responses API events (`event: response.output_text.delta\ndata: {...}\n\n`). Accepts either a live `chunk_iterator` (true streaming) or pre-built `full_text` (simulated streaming).

### Provider Abstraction
All providers inherit from `providers/base.py:LLMProvider`. Active providers:
- **`claude-cli`** — Claude Opus/Sonnet/Haiku via local CLI (handles OAuth internally)
- **`ollama`** — 7 local models across 2 GPU servers (10.0.0.9 + 10.0.0.10)

The singleton `providers/registry.py:provider_registry` initializes at startup. `get_provider_for_model()` prefers healthy providers.

### Key Singletons
- `provider_registry` (`providers/registry.py`) — provider instances + health state
- `metrics` (`common/metrics.py`) — in-memory counters, time-series, model leaderboard, request history (resets on restart)
- `settings` (`config/settings.py`) — Pydantic BaseSettings, `A1_` env prefix
- `session_manager` (`session/manager.py`) — conversation memory
- `pii_masker` (`security/pii_masker.py`) — PII detection engine

### Database
SQLAlchemy async with SQLiteUUID TypeDecorator for UUID↔string conversion. Dev uses SQLite (`a1_trainer.db`), prod uses PostgreSQL. Key tables: `conversations`, `messages`, `routing_decisions`, `dual_execution_records`, `task_type_readiness`, `usage_records`.

### Dashboard
11-page React SPA (Ant Design + Recharts + Zustand): Overview, Conversations, Routing, Providers, Accounts, Models, Playground, Training, Analytics, Import, Settings. API client in `dashboard-ui/src/lib/api.ts`.

## Configuration

All settings in `config/settings.py` with `A1_` prefix from `.env`:
- **Atlas models**: `A1_ATLAS_MODELS` (JSON array)
- **Distillation**: `A1_DISTILLATION_ENABLED`, `A1_DISTILLATION_CLAUDE_MODEL`, `A1_DISTILLATION_MIN_SAMPLES`
- **Session**: `A1_SESSION_ENABLED`, `A1_SESSION_TTL_SECONDS`, `A1_SESSION_MAX_MESSAGES`
- **PII**: `A1_PII_MASKING_ENABLED`, `A1_PII_MASK_FOR_EXTERNAL_ONLY`
- **Ollama**: `A1_OLLAMA_SERVERS` (JSON array of server URLs)
- **Routing**: `config/routing_policy.yaml` (task→model defaults), `config/providers.yaml` (model metadata)

## Conventions

- Async everywhere — DB, HTTP, subprocess calls all use async/await
- Ruff: line-length 100, target Python 3.11
- Dashboard: Ant Design components, Zustand stores, Axios in `lib/api.ts`
- Atlas model routing defined in `ATLAS_TASK_MAP` dicts within `proxy/router.py`
- `alpheric-1` is a backward-compatibility alias for `atlas-plan` (mapped in 3 places in router.py)
- Windows: always start uvicorn with `PYTHONIOENCODING=utf-8` or Claude CLI responses will crash on emojis
