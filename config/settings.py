from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "A1_"}

    # App
    app_name: str = "A1 Trainer"
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
    ollama_base_url: str = "http://localhost:11434"  # primary server
    ollama_servers: list[str] = [
        "http://10.0.0.9:11434",   # alpheric — code models (deepseek-coder, llama3.2)
        "http://10.0.0.10:11434",  # alpheric.com — QA/reasoning models (codellama, deepseek-r1, mistral)
    ]

    # Proxy auth
    api_keys: list[str] = []  # allowed API keys for proxy access

    # Routing
    exploration_rate: float = 0.1  # epsilon-greedy exploration
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

    # LiteLLM (provider engine)
    use_litellm: bool = True  # False reverts to native provider implementations

    # Unsloth (fast training)
    use_unsloth: bool = True  # False reverts to HuggingFace manual QLoRA

    # GPTCache (semantic caching)
    cache_enabled: bool = False
    cache_similarity_threshold: float = 0.8
    cache_ttl_seconds: int = 3600
    cache_embedding: str = "local"  # "local" (onnx) or "openai"
    cache_db_path: str = "./cache/gptcache.db"

    # OpenTelemetry
    otlp_endpoint: str = ""  # e.g., "http://localhost:4317" for Jaeger/Tempo

    # Argilla (human feedback)
    argilla_api_url: str = ""  # e.g., "http://localhost:6900"
    argilla_api_key: str = ""
    argilla_workspace: str = "default"

    # lm-evaluation-harness
    use_harness_eval: bool = False
    harness_default_tasks: list[str] = ["mmlu", "hellaswag", "truthfulqa_mc2"]
    harness_num_fewshot: int = 5
    harness_batch_size: int = 4

    # Multi-account key pool
    key_pool_strategy: str = "round_robin"  # round_robin, least_used, priority, budget_aware
    encryption_key: str = ""  # Fernet key for encrypting stored API keys

    # Multi-model management
    warm_up_models: list[str] = []  # Ollama models to preload on startup
    reference_external_model: str = "gpt-4o-mini"  # for savings calculation


settings = Settings()
