from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "A1_", "env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    # App
    app_name: str = "Alpheric.AI"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000

    # Database
    database_url: str = "postgresql+asyncpg://a1:a1_dev_password@localhost:5432/a1_trainer"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Provider API keys
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    vertex_project_id: str = ""
    vertex_location: str = "us-central1"

    # Ollama (supports multiple servers)
    ollama_base_url: str = "http://localhost:11434"
    ollama_servers: list[str] = [
        "http://10.0.0.9:11434",   # Code models (deepseek-coder, llama3.2)
        "http://10.0.0.10:11434",  # QA/reasoning models (codellama, deepseek-r1, mistral)
    ]

    # OpenClaw gateway
    openclaw_url: str = ""
    openclaw_token: str = ""

    # Atlas model family
    atlas_models: list[str] = [
        "atlas-plan", "atlas-code", "atlas-secure",
        "atlas-infra", "atlas-data", "atlas-books", "atlas-audit",
    ]

    # Proxy auth
    api_keys: list[str] = []

    # Routing
    exploration_rate: float = 0.1
    default_strategy: str = "best_quality"

    # Training
    training_min_samples: int = 500
    training_min_quality: float = 0.7
    training_base_model: str = "mistralai/Mistral-7B-Instruct-v0.3"
    training_lora_rank: int = 16
    training_output_dir: str = "./training_outputs"

    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # --- Open-source integrations ---
    use_litellm: bool = True
    use_unsloth: bool = True

    # GPTCache
    cache_enabled: bool = False
    cache_similarity_threshold: float = 0.8
    cache_ttl_seconds: int = 3600
    cache_embedding: str = "local"
    cache_db_path: str = "./cache/gptcache.db"

    # OpenTelemetry
    otlp_endpoint: str = ""

    # Argilla
    argilla_api_url: str = ""
    argilla_api_key: str = ""
    argilla_workspace: str = "default"
    argilla_handoff_gate_enabled: bool = True  # require Argilla annotation approval before handoff increment
    argilla_approval_threshold: float = 0.8    # fraction of annotated records rated ≥4/5 required for approval

    # lm-evaluation-harness
    use_harness_eval: bool = False
    harness_default_tasks: list[str] = ["mmlu", "hellaswag", "truthfulqa_mc2"]
    harness_num_fewshot: int = 5
    harness_batch_size: int = 4

    # Multi-account key pool
    key_pool_strategy: str = "round_robin"
    encryption_key: str = ""

    # Distillation / Auto-training
    distillation_enabled: bool = True
    distillation_claude_model: str = "claude-opus-4-20250514"
    distillation_min_samples: int = 100
    distillation_quality_threshold: float = 0.7
    distillation_handoff_increment: float = 0.1
    distillation_max_handoff_pct: float = 0.9

    # Session memory
    session_enabled: bool = True
    session_ttl_seconds: int = 3600  # 1 hour
    session_max_messages: int = 20  # max history to include per request

    # PII masking (enterprise)
    pii_masking_enabled: bool = True
    pii_mask_for_external_only: bool = True  # only mask for Claude, not Ollama
    pii_patterns: list[str] = ["email", "phone", "ssn", "credit_card", "api_key", "ip_address", "aws_key", "password"]

    # Groq
    groq_api_key: str = ""

    # Phase 1: performance
    parallel_dual_execution: bool = True          # fire local model concurrently with external
    session_load_grace_ms: int = 100              # max ms to wait for session before proceeding

    # Multi-model management
    warm_up_models: list[str] = []
    reference_external_model: str = "gpt-4o-mini"


settings = Settings()
