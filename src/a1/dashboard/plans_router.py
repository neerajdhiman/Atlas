"""Planning API endpoints.

Endpoints:
  POST /plans
  POST /plans/{plan_id}/execute
  GET  /plans
  GET  /plans/{plan_id}
"""

import asyncio
import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from a1.common.logging import get_logger
from a1.dependencies import get_db

log = get_logger("dashboard.plans")

router = APIRouter()


@router.post("/plans")
async def create_plan(body: dict):
    """Decompose a goal into subtasks using atlas-plan."""
    goal = body.get("goal", "")
    workspace_id = body.get("workspace_id", "")
    if not goal or not workspace_id:
        raise HTTPException(400, "goal and workspace_id are required")

    from a1.agents.planner import planning_engine

    plan_id = await planning_engine.create_plan(
        workspace_id=workspace_id,
        goal=goal,
        created_by=body.get("created_by"),
    )
    return {"plan_id": plan_id, "status": "planning"}


@router.post("/plans/{plan_id}/execute")
async def execute_plan(plan_id: str):
    """Execute a plan's subtasks in dependency order."""
    from a1.agents.planner import planning_engine

    async def _run():
        result = await planning_engine.execute_plan(plan_id)
        log.info(f"[plan] {plan_id} execution finished: {'completed' if result else 'failed'}")

    asyncio.create_task(_run())
    return {"plan_id": plan_id, "status": "executing"}


@router.get("/plans")
async def list_plans(
    workspace_id: str | None = Query(None),
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """List task plans."""
    from sqlalchemy import select

    from a1.db.models import TaskPlan

    stmt = select(TaskPlan).order_by(TaskPlan.created_at.desc()).limit(50)
    if workspace_id:
        stmt = stmt.where(TaskPlan.workspace_id == _uuid.UUID(workspace_id))
    if status:
        stmt = stmt.where(TaskPlan.status == status)

    result = await db.execute(stmt)
    plans = result.scalars().all()
    return {
        "data": [
            {
                "id": str(p.id),
                "root_task": p.root_task[:200],
                "status": p.status,
                "steps_completed": p.steps_completed,
                "steps_total": p.steps_total,
                "workspace_id": str(p.workspace_id),
                "created_at": p.created_at,
                "completed_at": p.completed_at,
            }
            for p in plans
        ]
    }


@router.get("/plans/{plan_id}")
async def get_plan(plan_id: str, db: AsyncSession = Depends(get_db)):
    """Get a plan with full decomposition and result."""
    from sqlalchemy import select

    from a1.db.models import TaskPlan

    result = await db.execute(select(TaskPlan).where(TaskPlan.id == _uuid.UUID(plan_id)))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(404, "Plan not found")
    return {
        "id": str(plan.id),
        "root_task": plan.root_task,
        "decomposed": plan.decomposed,
        "status": plan.status,
        "result": plan.result,
        "steps_completed": plan.steps_completed,
        "steps_total": plan.steps_total,
        "workspace_id": str(plan.workspace_id),
        "created_at": plan.created_at,
        "completed_at": plan.completed_at,
    }
