# A1 Trainer — OneDesk AI/LLM Middleware & Training Platform

## What It Does
A smart proxy that sits between your apps and external LLM providers (Claude, GPT, Gemini, 100+ models). It automatically routes each request to the best model for the job, collects quality data, and uses it to fine-tune local models that get better over time.

## Architecture

```
                        ┌─────────────────────────────────────┐
                        │          A1 Trainer Proxy            │
  Any OpenAI-           │                                     │
  compatible   ───────► │  Classify ► Route ► Cache ► Call    │
  client                │     │         │              │      │
                        │     ▼         ▼              ▼      │
                        │  Task Type  Best Model    Provider   │
                        │  (code,     (by quality,  (Anthropic,│
                        │   chat,      cost, or     OpenAI,    │
                        │   math...)   latency)     Vertex,    │
                        │                           Ollama)    │
                        └──────────────┬──────────────────────┘
                                       │
                           ┌───────────┼───────────┐
                           ▼           ▼           ▼
                     ┌──────────┐ ┌─────────┐ ┌──────────┐
                     │PostgreSQL│ │  Redis   │ │  Ollama  │
                     │(history, │ │(cache,   │ │(local    │
                     │ metrics) │ │ queue)   │ │ models)  │
                     └──────────┘ └─────────┘ └──────────┘
                           │
                           ▼
                     ┌──────────────────────┐
                     │   Training Pipeline   │
                     │  Collect ► Train ►    │
                     │  Evaluate ► Deploy    │
                     │  (Unsloth QLoRA)      │
                     └──────────────────────┘
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python FastAPI (async) |
| Provider Engine | LiteLLM (100+ models, auto-translation) |
| Database | PostgreSQL + SQLAlchemy async |
| Cache/Queue | Redis + GPTCache (semantic) |
| Training | Unsloth (2-5x faster QLoRA) + HuggingFace |
| Evaluation | lm-evaluation-harness (MMLU, HumanEval, etc.) |
| Feedback | Argilla (human annotation) |
| Observability | OpenTelemetry → Jaeger/Grafana |
| Local Models | Ollama |
| Dashboard | React + Vite + TailwindCSS + Recharts |

## Project Structure

```
A1_Trainer/
├── src/a1/
│   ├── proxy/          # OpenAI-compatible /v1/chat/completions endpoint
│   ├── providers/      # LiteLLM + Ollama provider abstraction
│   ├── routing/        # Smart ML-based task classification + model selection
│   ├── training/       # Unsloth QLoRA pipeline (collect→train→eval→deploy)
│   ├── feedback/       # Argilla human feedback integration
│   ├── importers/      # paperclip.ing + OpenAI JSONL import
│   ├── dashboard/      # Admin API + WebSocket live feed
│   ├── db/             # PostgreSQL models + repositories
│   └── common/         # Auth, logging, metrics, telemetry, tokens
├── dashboard-ui/       # React SPA (8 pages)
├── config/             # Settings, provider registry, routing policy
├── alembic/            # Database migrations
├── docker-compose.yml  # Postgres, Redis, Ollama, Argilla, Jaeger
└── tests/
```

## Key Features

### Smart Proxy (OpenAI-compatible)
- Drop-in replacement: point `OPENAI_BASE_URL` at A1 Trainer
- Special model aliases: `auto` (best quality), `auto:fast`, `auto:cheap`, `local`
- Streaming + non-streaming support
- Request/response logging to DB

### Smart Router
- Rule-based task classifier (code, chat, math, analysis, creative, etc.)
- Model scorer picks best provider by quality, cost, or latency
- Epsilon-greedy exploration (10%) to keep discovering better models
- Fallback chain on provider failure (same provider → different provider → local)

### Training Pipeline
- Collects high-quality conversations (filtered by user feedback)
- QLoRA fine-tuning via Unsloth (2-5x faster than vanilla HuggingFace)
- Evaluation via lm-eval-harness (MMLU, HellaSwag, HumanEval)
- Auto-deploy to Ollama if improvement > 2%

### Full Dashboard
- **Overview**: Real-time stats, provider/task distribution charts, live request feed
- **Conversations**: Search, browse, replay with routing decisions + quality signals
- **Routing**: Model leaderboard, decision log, task type distribution
- **Providers**: Health status, model listing, latency/cost metrics
- **Training**: Run management, progress, eval metrics, deploy status
- **Analytics**: Cost by provider, latency by model, token usage, trends
- **Import**: paperclip.ing + JSONL import
- **Settings**: Provider keys, routing policy, training config

### Open-Source Integrations (all feature-flagged)
| Tool | Purpose | Flag |
|------|---------|------|
| LiteLLM | 100+ model support | `A1_USE_LITELLM=true` |
| Unsloth | 2-5x faster training | `A1_USE_UNSLOTH=true` |
| GPTCache | Semantic caching | `A1_CACHE_ENABLED=false` |
| OpenTelemetry | Traces + metrics | `A1_OTLP_ENDPOINT=` |
| Argilla | Human feedback | `A1_ARGILLA_API_URL=` |
| lm-eval-harness | Benchmarks | `A1_USE_HARNESS_EVAL=false` |

## Quick Start

```bash
# 1. Start infrastructure
docker compose up -d                    # Postgres, Redis, Ollama

# 2. Optional services
docker compose --profile observability up -d   # + Jaeger
docker compose --profile feedback up -d        # + Argilla

# 3. Install + configure
cp .env.example .env                    # Edit API keys
pip install -e ".[dev]"                 # Python deps
cd dashboard-ui && npm install && cd .. # Dashboard deps

# 4. Database
alembic upgrade head

# 5. Run
uvicorn a1.app:app --reload             # Backend on :8000
cd dashboard-ui && npm run dev          # Dashboard on :5173

# 6. Test
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "auto", "messages": [{"role": "user", "content": "Hello"}]}'
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/chat/completions` | POST | OpenAI-compatible proxy (main endpoint) |
| `/v1/models` | GET | List all available models |
| `/admin/overview` | GET | Dashboard overview stats |
| `/admin/conversations` | GET | List conversations |
| `/admin/routing/decisions` | GET | Recent routing decisions |
| `/admin/routing/performance` | GET | Model leaderboard |
| `/admin/providers` | GET | Provider health + models |
| `/admin/training/runs` | GET/POST | Training run management |
| `/admin/argilla/export` | POST | Export to Argilla for annotation |
| `/admin/argilla/import` | POST | Import annotations |
| `/admin/import/paperclip` | POST | Import from paperclip.ing |
| `/admin/metrics` | GET | System metrics |
| `/ws/live-feed` | WS | Real-time request stream |
| `/health` | GET | Health check |

## File Count
- **82 files**, **~6,100 lines of code**
- Backend: 35 Python files
- Dashboard: 16 TypeScript/TSX files
- Config: 6 files
