"""Auth and settings endpoints for the dashboard.

Auth:
  POST /auth/login   — accept username/password (password = API key in production,
                       any value accepted in dev mode). Returns token + user object.
  POST /auth/refresh — refresh an existing token
  GET  /auth/me      — return the currently authenticated user

Settings:
  GET  /settings     — return current (redacted) configuration
  PUT  /settings     — accept new settings (runtime-only; persists nothing to disk)
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from a1.common.auth import AuthContext, get_auth_context
from config.settings import settings

router = APIRouter(tags=["auth"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    token: str
    refresh_token: str
    user: dict


class RefreshRequest(BaseModel):
    refresh_token: str


# ---------------------------------------------------------------------------
# Auth endpoints (no top-level auth dependency — login must be public)
# ---------------------------------------------------------------------------


@router.post("/auth/login", response_model=TokenResponse)
async def login(body: LoginRequest):
    """Authenticate with username + password (password = API key in prod).

    In dev mode (no A1_API_KEYS configured) any credentials are accepted and
    a synthetic 'dev' token is returned.
    """
    if not settings.api_keys:
        # Dev mode — accept anything
        return {
            "token": "dev",
            "refresh_token": "dev-refresh",
            "user": {
                "id": "dev",
                "username": body.username or "admin",
                "email": f"{body.username or 'admin'}@localhost",
                "role": "admin",
            },
        }

    # Production mode — password IS the API key
    api_key = body.password
    if api_key not in settings.api_keys:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return {
        "token": api_key,
        "refresh_token": api_key,  # stateless: token == refresh token
        "user": {
            "id": "admin",
            "username": body.username,
            "email": f"{body.username}@alpheric.ai",
            "role": "admin",
        },
    }


@router.post("/auth/refresh")
async def refresh_token(body: RefreshRequest):
    """Refresh a session token. In stateless mode the same token is returned."""
    if not settings.api_keys:
        return {"token": "dev", "refresh_token": "dev-refresh"}

    token = body.refresh_token
    if token not in settings.api_keys:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    return {"token": token, "refresh_token": token}


@router.get("/auth/me")
async def get_current_user(auth: AuthContext = Depends(get_auth_context)):
    """Return the identity of the currently authenticated caller."""
    return {
        "id": auth.user_id or auth.key_hash or "dev",
        "username": "admin",
        "email": "admin@alpheric.ai",
        "role": auth.role,
        "workspace_id": auth.workspace_id,
    }


# ---------------------------------------------------------------------------
# Settings endpoints
# ---------------------------------------------------------------------------

# Fields exposed to the dashboard (never expose raw secrets)
_REDACTED = "••••••••"


def _mask(value: str | None) -> str:
    return _REDACTED if value else ""


@router.get("/settings")
async def get_settings():
    """Return current configuration (API keys redacted)."""
    return {
        "anthropic_api_key": _mask(settings.anthropic_api_key),
        "openai_api_key": _mask(settings.openai_api_key),
        "vertex_project_id": settings.vertex_project_id or "",
        "ollama_base_url": settings.ollama_base_url or "",
        "default_strategy": settings.default_strategy,
        "exploration_rate": settings.exploration_rate,
        "training_base_model": settings.training_base_model,
        "training_lora_rank": settings.training_lora_rank,
        "training_min_quality": settings.training_min_quality,
        "training_min_samples": settings.training_min_samples,
        "distillation_enabled": settings.distillation_enabled,
        "pii_masking_enabled": settings.pii_masking_enabled,
        "session_enabled": settings.session_enabled,
        "cache_enabled": settings.cache_enabled,
        "debug": settings.debug,
    }


@router.put("/settings")
async def save_settings(body: dict):
    """Accept settings from the dashboard.

    Runtime-only: values take effect for the duration of this process.
    Restart the server after editing .env to persist changes permanently.
    """
    changed: list[str] = []

    # Apply safe, non-secret settings at runtime
    safe_fields = {
        "default_strategy": str,
        "exploration_rate": float,
        "training_lora_rank": int,
        "training_min_quality": float,
        "training_min_samples": int,
        "debug": bool,
    }
    for field, cast in safe_fields.items():
        if field in body:
            try:
                setattr(settings, field, cast(body[field]))
                changed.append(field)
            except Exception:
                pass

    return {"status": "ok", "applied": changed, "note": "Restart server to persist changes."}
