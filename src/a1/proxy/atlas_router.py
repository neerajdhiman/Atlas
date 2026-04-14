"""Alpheric.AI Atlas endpoint: /atlas and /atlas/models.

Thin adapter that parses Atlas-native request format, applies agent persona
injection, normalizes into CorePipelineInput, delegates to CorePipeline,
and formats the result as Responses API JSON.
"""

import uuid

from fastapi import APIRouter, Depends, Response

from a1.common.auth import verify_api_key
from a1.common.logging import get_logger
from a1.proxy.core_pipeline import CorePipelineInput, core_pipeline, request_id_var
from a1.proxy.pipeline import _return_response_or_stream
from a1.proxy.request_models import MessageInput
from a1.routing.atlas_models import ATLAS_TASK_ROUTING
from config.settings import settings

log = get_logger("proxy.atlas")
router = APIRouter()


def _parse_atlas_input(request: dict) -> tuple[list[MessageInput], str, str]:
    """Parse Atlas-native input format into messages list.

    Returns (messages, raw_user_input, model).
    """
    model = request.get("model", "atlas")
    input_data = request.get("input", "")
    instructions = request.get("instructions", "")
    tools = request.get("tools", [])

    # Agent persona injection
    agent_id = request.get("agent_id")
    atlas_model_override = None
    if agent_id:
        from a1.agents.registry import agent_registry

        agent = agent_registry.get_by_id(agent_id)
        # Workspace scoping: verify agent belongs to same workspace as request
        # (workspace_id will be set when auth middleware provides it)
        if agent and agent.status == "active":
            atlas_model_override = agent.atlas_model
            model = agent.atlas_model
            persona_parts = []
            if agent.system_prompt:
                persona_parts.append(agent.system_prompt)
            if instructions:
                persona_parts.append(instructions)
            instructions = "\n\n".join(persona_parts) if persona_parts else instructions
            if agent.tools:
                existing = {t.get("name", "") for t in tools if isinstance(t, dict)}
                for tn in agent.tools:
                    if tn not in existing:
                        tools.append({"name": tn, "description": ""})
            log.info(f"[atlas] Agent '{agent.name}' ({agent.atlas_model}) injected")
        else:
            log.warning(f"[atlas] agent_id={agent_id} not found or inactive")

    # Build messages
    messages = []

    # System prompt from instructions + tools
    system_parts = []
    if instructions:
        system_parts.append(instructions)
    if tools:
        tool_descs = []
        for t in tools:
            name = t.get("name", t.get("function", {}).get("name", "unknown"))
            desc = t.get("description", t.get("function", {}).get("description", ""))
            tool_descs.append(f"- {name}: {desc}")
        if tool_descs:
            system_parts.append("\n\nAvailable tools:\n" + "\n".join(tool_descs))
    if system_parts:
        messages.append(MessageInput(role="system", content="\n".join(system_parts)))

    # User input
    raw_user_input = ""
    if isinstance(input_data, str):
        messages.append(MessageInput(role="user", content=input_data))
        raw_user_input = input_data
    elif isinstance(input_data, list):
        for msg in input_data:
            if isinstance(msg, dict):
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if isinstance(content, list):
                    content = " ".join(p.get("text", "") for p in content if isinstance(p, dict))
                messages.append(MessageInput(role=role, content=content))
                if role == "user":
                    raw_user_input = content
            elif isinstance(msg, str):
                messages.append(MessageInput(role="user", content=msg))
                raw_user_input = msg

    if not messages:
        messages.append(MessageInput(role="user", content="Hello"))
        raw_user_input = "Hello"

    return messages, raw_user_input, model, atlas_model_override


@router.post("/atlas")
async def atlas_endpoint(
    request: dict,
    response: Response,
    api_key: str = Depends(verify_api_key),
):
    """Alpheric.AI Atlas endpoint -- auto-selects the right model."""
    rid = request_id_var.get("")

    messages, raw_user_input, model, atlas_model_override = _parse_atlas_input(request)

    inp = CorePipelineInput(
        request_id=rid or f"resp_{uuid.uuid4().hex[:12]}",
        source="atlas",
        messages=messages,
        raw_user_input=raw_user_input,
        model=model,
        atlas_model_override=atlas_model_override,
        strategy="best_quality",
        temperature=request.get("temperature"),
        max_tokens=request.get("max_output_tokens") or request.get("max_tokens", 1000),
        stream=request.get("stream", False),
        session_id=request.get("session_id"),
        previous_response_id=request.get("previous_response_id"),
        user_id=request.get("user"),
        use_llm_classifier=True,  # Atlas uses LLM fallback classifier
    )

    result = await core_pipeline.execute(inp, response)

    # Set response headers
    if result.atlas_model:
        response.headers["X-Atlas-Model"] = result.atlas_model
    response.headers["X-Atlas-Provider"] = result.provider_name or "unknown"

    # Handle errors
    if result.error and not result.assistant_text:
        return {
            "id": result.response_id,
            "object": "response",
            "status": "failed",
            "error": {"type": result.error_type or "internal_error", "message": result.error},
            "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        }

    # Streaming
    if result.chunk_iterator:
        meta = {
            "provider": result.provider_name,
            "is_local": result.is_local,
            "task_type": result.task_type,
            "atlas_model": result.atlas_model,
            "distillation": result.distillation,
            "session_id": result.session_id,
        }
        return await _return_response_or_stream(
            True,
            result.response_id,
            result.atlas_model or result.model_name,
            None,
            {},
            meta,
            chunk_iterator=result.chunk_iterator,
        )

    # Non-streaming JSON response
    usage = {
        "input_tokens": result.prompt_tokens,
        "output_tokens": result.completion_tokens,
        "total_tokens": result.total_tokens,
    }
    meta = {
        "provider": result.provider_name,
        "is_local": result.is_local,
        "task_type": result.task_type,
        "atlas_model": result.atlas_model,
        "distillation": result.distillation,
        "latency_ms": result.latency_ms,
        "session_id": result.session_id,
        "pii_masked": result.pii_masked,
    }
    return await _return_response_or_stream(
        False,
        result.response_id,
        result.atlas_model or result.model_name or inp.model,
        result.assistant_text or "",
        usage,
        meta,
    )


@router.get("/atlas/models")
async def atlas_models(api_key: str = Depends(verify_api_key)):
    """List all Atlas model family members."""
    import yaml

    try:
        with open("config/providers.yaml") as f:
            cfg = yaml.safe_load(f)
        atlas_cfg = cfg.get("providers", {}).get("atlas", {}).get("models", [])
    except Exception:
        atlas_cfg = []

    models = []
    for m in atlas_cfg:
        models.append(
            {
                "id": m.get("name"),
                "tasks": m.get("task_types", []),
                "description": m.get("description", ""),
                "context_window": m.get("context_window", 128000),
            }
        )

    if not models:
        # Fallback to hardcoded list
        for name, info in ATLAS_TASK_ROUTING.items():
            models.append(
                {
                    "id": name,
                    "tasks": info.get("tasks", []),
                    "description": info.get("description", ""),
                    "context_window": 128000,
                }
            )

    return {
        "object": "list",
        "family": "Atlas",
        "product": settings.app_name,
        "models": models,
    }
