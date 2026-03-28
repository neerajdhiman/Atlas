"""Proxy router — aggregates all sub-routers into a single FastAPI router.

Sub-routers:
  openai_router   — /v1/chat/completions, /v1/models
  responses_router — /v1/responses
  atlas_router    — /atlas, /atlas/models
"""

from fastapi import APIRouter

from a1.proxy.openai_router import router as _openai
from a1.proxy.responses_router import router as _responses
from a1.proxy.atlas_router import router as _atlas

router = APIRouter(tags=["proxy"])
router.include_router(_openai)
router.include_router(_responses)
router.include_router(_atlas)
