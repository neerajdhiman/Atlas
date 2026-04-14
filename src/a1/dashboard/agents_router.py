"""Agents, applications, and workspaces CRUD endpoints.

Endpoints:
  GET    /agents
  POST   /agents
  GET    /agents/{agent_id}
  PATCH  /agents/{agent_id}
  DELETE /agents/{agent_id}
  POST   /agents/{agent_id}/run
  GET    /applications
  POST   /applications
  GET    /applications/{app_id}
  PATCH  /applications/{app_id}
  DELETE /applications/{app_id}
  GET    /workspaces
  POST   /workspaces
"""

import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from a1.dependencies import get_db

router = APIRouter()


# ---------------------------------------------------------------------------
# Agents API
# ---------------------------------------------------------------------------


@router.get("/agents")
async def list_agents(workspace_id: str | None = Query(None)):
    """List all agents, optionally filtered by workspace."""
    from a1.agents.registry import agent_registry

    agents = agent_registry.list_agents(workspace_id=workspace_id)
    return {
        "data": [
            {
                "id": a.id,
                "name": a.name,
                "display_name": a.display_name,
                "atlas_model": a.atlas_model,
                "status": a.status,
                "workspace_id": a.workspace_id,
                "app_id": a.app_id,
                "tools": a.tools,
                "parent_id": a.parent_id,
            }
            for a in agents
        ]
    }


@router.post("/agents")
async def create_agent(body: dict, db: AsyncSession = Depends(get_db)):
    """Create a new agent."""
    from a1.db.models import Agent

    required = {"workspace_id", "name", "display_name"}
    missing = required - body.keys()
    if missing:
        raise HTTPException(400, f"Missing required fields: {missing}")

    agent = Agent(
        id=_uuid.uuid4(),
        workspace_id=_uuid.UUID(body["workspace_id"]),
        app_id=_uuid.UUID(body["app_id"]) if body.get("app_id") else None,
        name=body["name"],
        display_name=body["display_name"],
        atlas_model=body.get("atlas_model", "atlas-plan"),
        system_prompt=body.get("system_prompt"),
        tools=body.get("tools", []),
        memory_config=body.get("memory_config", {"type": "sliding_window", "limit": 20}),
        parent_id=_uuid.UUID(body["parent_id"]) if body.get("parent_id") else None,
        status="active",
        metadata_=body.get("metadata", {}),
        created_by=body.get("created_by"),
    )
    db.add(agent)
    await db.flush()
    await db.commit()

    from a1.agents.registry import agent_registry

    await agent_registry.invalidate()
    return {"id": str(agent.id), "name": agent.name, "status": "created"}


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str):
    """Get a single agent by ID."""
    from a1.agents.registry import agent_registry

    agent = agent_registry.get_by_id(agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")
    return {
        "id": agent.id,
        "name": agent.name,
        "display_name": agent.display_name,
        "atlas_model": agent.atlas_model,
        "system_prompt": agent.system_prompt,
        "tools": agent.tools,
        "memory_config": agent.memory_config,
        "status": agent.status,
        "workspace_id": agent.workspace_id,
        "app_id": agent.app_id,
        "parent_id": agent.parent_id,
    }


@router.patch("/agents/{agent_id}")
async def update_agent(agent_id: str, body: dict, db: AsyncSession = Depends(get_db)):
    """Update an agent (partial update)."""
    from sqlalchemy import select

    from a1.db.models import Agent

    result = await db.execute(select(Agent).where(Agent.id == _uuid.UUID(agent_id)))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(404, "Agent not found")

    updatable = {
        "display_name",
        "atlas_model",
        "system_prompt",
        "tools",
        "memory_config",
        "status",
        "metadata",
    }
    for field in updatable:
        if field in body:
            setattr(agent, field if field != "metadata" else "metadata_", body[field])

    await db.commit()
    from a1.agents.registry import agent_registry

    await agent_registry.invalidate(agent_id)
    return {"id": agent_id, "status": "updated"}


@router.delete("/agents/{agent_id}")
async def delete_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    """Soft-delete an agent (sets status=terminated)."""
    from sqlalchemy import select

    from a1.db.models import Agent

    result = await db.execute(select(Agent).where(Agent.id == _uuid.UUID(agent_id)))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(404, "Agent not found")

    agent.status = "terminated"
    await db.commit()
    from a1.agents.registry import agent_registry

    await agent_registry.invalidate(agent_id)
    return {"id": agent_id, "status": "terminated"}


@router.post("/agents/{agent_id}/run")
async def run_agent_task(agent_id: str, body: dict):
    """Run an agent on a task and return the result."""
    task = body.get("task", "")
    if not task:
        raise HTTPException(400, "task is required")
    from a1.agents.executor import run_agent_by_id

    result = await run_agent_by_id(
        agent_id=agent_id,
        task=task,
        extra_messages=body.get("messages"),
        max_tokens=body.get("max_tokens", 2000),
    )
    if result is None:
        raise HTTPException(503, "Agent execution failed or agent not found")
    return {"agent_id": agent_id, "result": result}


# ---------------------------------------------------------------------------
# Applications API
# ---------------------------------------------------------------------------


@router.get("/applications")
async def list_applications(
    workspace_id: str | None = Query(None), db: AsyncSession = Depends(get_db)
):
    """List all applications."""
    from sqlalchemy import select

    from a1.db.models import Application

    stmt = select(Application).where(Application.is_active.is_(True))
    if workspace_id:
        stmt = stmt.where(Application.workspace_id == _uuid.UUID(workspace_id))
    result = await db.execute(stmt)
    apps = result.scalars().all()
    return {
        "data": [
            {
                "id": str(a.id),
                "name": a.name,
                "display_name": a.display_name,
                "atlas_model": a.atlas_model,
                "workspace_id": str(a.workspace_id),
                "tools": a.tools,
                "rate_limit_rpm": a.rate_limit_rpm,
                "created_at": a.created_at,
            }
            for a in apps
        ]
    }


@router.post("/applications")
async def create_application(body: dict, db: AsyncSession = Depends(get_db)):
    """Create a new application."""
    from a1.db.models import Application

    required = {"workspace_id", "name", "display_name"}
    missing = required - body.keys()
    if missing:
        raise HTTPException(400, f"Missing required fields: {missing}")

    app = Application(
        id=_uuid.uuid4(),
        workspace_id=_uuid.UUID(body["workspace_id"]),
        name=body["name"],
        display_name=body["display_name"],
        atlas_model=body.get("atlas_model", "atlas-plan"),
        system_prompt=body.get("system_prompt"),
        tools=body.get("tools", []),
        agent_pool=body.get("agent_pool", []),
        rate_limit_rpm=body.get("rate_limit_rpm", 60),
        app_settings=body.get("settings", {}),
        created_by=body.get("created_by"),
    )
    db.add(app)
    await db.flush()
    return {"id": str(app.id), "name": app.name, "status": "created"}


@router.get("/applications/{app_id}")
async def get_application(app_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single application."""
    from sqlalchemy import select

    from a1.db.models import Application

    result = await db.execute(select(Application).where(Application.id == _uuid.UUID(app_id)))
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(404, "Application not found")
    return {
        "id": str(app.id),
        "name": app.name,
        "display_name": app.display_name,
        "atlas_model": app.atlas_model,
        "system_prompt": app.system_prompt,
        "tools": app.tools,
        "agent_pool": app.agent_pool,
        "rate_limit_rpm": app.rate_limit_rpm,
        "workspace_id": str(app.workspace_id),
        "settings": app.app_settings,
        "created_at": app.created_at,
    }


@router.patch("/applications/{app_id}")
async def update_application(app_id: str, body: dict, db: AsyncSession = Depends(get_db)):
    """Update an application (partial update)."""
    from sqlalchemy import select

    from a1.db.models import Application

    result = await db.execute(select(Application).where(Application.id == _uuid.UUID(app_id)))
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(404, "Application not found")

    for field in {
        "display_name",
        "atlas_model",
        "system_prompt",
        "tools",
        "agent_pool",
        "rate_limit_rpm",
    }:
        if field in body:
            setattr(app, field, body[field])
    return {"id": app_id, "status": "updated"}


@router.delete("/applications/{app_id}")
async def delete_application(app_id: str, db: AsyncSession = Depends(get_db)):
    """Soft-delete an application."""
    from sqlalchemy import select

    from a1.db.models import Application

    result = await db.execute(select(Application).where(Application.id == _uuid.UUID(app_id)))
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(404, "Application not found")

    app.is_active = False
    return {"id": app_id, "status": "deleted"}


# ---------------------------------------------------------------------------
# Workspaces API
# ---------------------------------------------------------------------------


@router.get("/workspaces")
async def list_workspaces(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select

    from a1.db.models import Workspace

    result = await db.execute(select(Workspace))
    workspaces = result.scalars().all()
    return {
        "data": [
            {"id": str(w.id), "name": w.name, "slug": w.slug, "created_at": w.created_at}
            for w in workspaces
        ]
    }


@router.post("/workspaces")
async def create_workspace(body: dict, db: AsyncSession = Depends(get_db)):
    from a1.db.models import Workspace

    if not body.get("name") or not body.get("slug"):
        raise HTTPException(400, "name and slug are required")

    workspace = Workspace(
        id=_uuid.uuid4(),
        name=body["name"],
        slug=body["slug"],
        settings=body.get("settings", {}),
    )
    db.add(workspace)
    await db.flush()
    return {"id": str(workspace.id), "slug": workspace.slug, "status": "created"}
