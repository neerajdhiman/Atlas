"""Notebook API — CRUD for notebooks and cells, plus execution."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from a1.common.auth import verify_api_key
from a1.common.logging import get_logger
from a1.common.tz import now_ist
from a1.dependencies import get_db

log = get_logger("notebook.router")

router = APIRouter(prefix="/notebooks", tags=["notebooks"], dependencies=[Depends(verify_api_key)])


# ---------------------------------------------------------------------------
# Notebooks CRUD
# ---------------------------------------------------------------------------


@router.get("")
async def list_notebooks(
    workspace_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    from a1.db.models import Notebook

    stmt = select(Notebook).order_by(Notebook.updated_at.desc()).limit(50)
    if workspace_id:
        stmt = stmt.where(Notebook.workspace_id == uuid.UUID(workspace_id))
    result = await db.execute(stmt)
    notebooks = result.scalars().all()
    return {
        "data": [
            {
                "id": str(n.id),
                "title": n.title,
                "kernel": n.kernel,
                "atlas_model": n.atlas_model,
                "workspace_id": str(n.workspace_id),
                "created_at": n.created_at,
                "updated_at": n.updated_at,
            }
            for n in notebooks
        ]
    }


@router.post("")
async def create_notebook(body: dict, db: AsyncSession = Depends(get_db)):
    from a1.db.models import Notebook

    if not body.get("workspace_id") or not body.get("title"):
        raise HTTPException(400, "workspace_id and title are required")

    notebook = Notebook(
        id=uuid.uuid4(),
        workspace_id=uuid.UUID(body["workspace_id"]),
        title=body["title"],
        kernel=body.get("kernel", "python"),
        atlas_model=body.get("atlas_model", "atlas-code"),
        created_by=body.get("created_by"),
    )
    db.add(notebook)
    await db.flush()
    return {"id": str(notebook.id), "title": notebook.title, "status": "created"}


@router.get("/{notebook_id}")
async def get_notebook(notebook_id: str, db: AsyncSession = Depends(get_db)):
    from a1.db.models import Notebook, NotebookCell

    result = await db.execute(select(Notebook).where(Notebook.id == uuid.UUID(notebook_id)))
    nb = result.scalar_one_or_none()
    if not nb:
        raise HTTPException(404, "Notebook not found")

    cells_result = await db.execute(
        select(NotebookCell)
        .where(NotebookCell.notebook_id == uuid.UUID(notebook_id))
        .order_by(NotebookCell.sequence)
    )
    cells = cells_result.scalars().all()

    return {
        "id": str(nb.id),
        "title": nb.title,
        "kernel": nb.kernel,
        "atlas_model": nb.atlas_model,
        "workspace_id": str(nb.workspace_id),
        "created_at": nb.created_at,
        "cells": [
            {
                "id": str(c.id),
                "sequence": c.sequence,
                "cell_type": c.cell_type,
                "source": c.source,
                "output": c.output,
                "ai_suggestion": c.ai_suggestion,
                "execution_state": c.execution_state,
                "executed_at": c.executed_at,
            }
            for c in cells
        ],
    }


@router.delete("/{notebook_id}")
async def delete_notebook(notebook_id: str, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import delete as sa_delete

    from a1.db.models import Notebook

    await db.execute(sa_delete(Notebook).where(Notebook.id == uuid.UUID(notebook_id)))
    return {"id": notebook_id, "status": "deleted"}


# ---------------------------------------------------------------------------
# Cells CRUD + Execution
# ---------------------------------------------------------------------------


@router.post("/{notebook_id}/cells")
async def add_cell(notebook_id: str, body: dict, db: AsyncSession = Depends(get_db)):
    # Get next sequence number
    from sqlalchemy import func

    from a1.db.models import NotebookCell

    result = await db.execute(
        select(func.coalesce(func.max(NotebookCell.sequence), -1)).where(
            NotebookCell.notebook_id == uuid.UUID(notebook_id)
        )
    )
    max_seq = result.scalar() or -1

    cell = NotebookCell(
        id=uuid.uuid4(),
        notebook_id=uuid.UUID(notebook_id),
        sequence=max_seq + 1,
        cell_type=body.get("cell_type", "code"),
        source=body.get("source", ""),
    )
    db.add(cell)
    await db.flush()
    return {"id": str(cell.id), "sequence": cell.sequence, "status": "created"}


@router.patch("/{notebook_id}/cells/{cell_id}")
async def update_cell(
    notebook_id: str, cell_id: str, body: dict, db: AsyncSession = Depends(get_db)
):
    from a1.db.models import NotebookCell

    result = await db.execute(select(NotebookCell).where(NotebookCell.id == uuid.UUID(cell_id)))
    cell = result.scalar_one_or_none()
    if not cell:
        raise HTTPException(404, "Cell not found")

    for field in ("source", "cell_type"):
        if field in body:
            setattr(cell, field, body[field])
    return {"id": cell_id, "status": "updated"}


@router.delete("/{notebook_id}/cells/{cell_id}")
async def delete_cell(notebook_id: str, cell_id: str, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import delete as sa_delete

    from a1.db.models import NotebookCell

    await db.execute(sa_delete(NotebookCell).where(NotebookCell.id == uuid.UUID(cell_id)))
    return {"id": cell_id, "status": "deleted"}


@router.post("/{notebook_id}/cells/{cell_id}/run")
async def run_cell(notebook_id: str, cell_id: str, db: AsyncSession = Depends(get_db)):
    """Execute a cell and return output + AI suggestion."""
    from a1.db.models import Notebook, NotebookCell

    # Load cell and notebook
    cell_result = await db.execute(
        select(NotebookCell).where(NotebookCell.id == uuid.UUID(cell_id))
    )
    cell = cell_result.scalar_one_or_none()
    if not cell:
        raise HTTPException(404, "Cell not found")

    nb_result = await db.execute(select(Notebook).where(Notebook.id == uuid.UUID(notebook_id)))
    nb = nb_result.scalar_one_or_none()
    if not nb:
        raise HTTPException(404, "Notebook not found")

    # Mark as running
    cell.execution_state = "running"
    await db.commit()

    # Execute
    from a1.notebook.kernel import execute_cell

    result = await execute_cell(
        source=cell.source,
        kernel=nb.kernel,
        atlas_model=nb.atlas_model,
    )

    # Update cell with results (new session since we committed)
    from a1.db.engine import async_session

    async with async_session() as session2:
        async with session2.begin():
            from sqlalchemy import update

            await session2.execute(
                update(NotebookCell)
                .where(NotebookCell.id == uuid.UUID(cell_id))
                .values(
                    output=result["output"],
                    ai_suggestion=result.get("ai_suggestion"),
                    execution_state="error" if result.get("error") else "completed",
                    executed_at=now_ist(),
                )
            )

    return {
        "cell_id": cell_id,
        "output": result["output"],
        "ai_suggestion": result.get("ai_suggestion"),
        "execution_state": "error" if result.get("error") else "completed",
    }
