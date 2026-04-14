"""PlanningEngine — CEO/Manager/Worker task decomposition and execution.

The atlas-plan model acts as CEO: it decomposes a high-level goal into
a tree of subtasks, assigns each to the best Atlas model (or named agent),
then executes them in dependency order, collecting results upward.

Usage:
    plan_id = await planning_engine.create_plan(workspace_id, goal)
    result  = await planning_engine.execute_plan(plan_id)
"""

import asyncio
import json
import time
import uuid
from dataclasses import dataclass

from a1.common.logging import get_logger
from a1.common.tz import now_ist
from config.settings import settings

log = get_logger("agents.planner")

_DECOMPOSE_PROMPT = """\
You are Atlas-Plan, a task decomposition engine by Alpheric.AI.

Given a user goal, decompose it into 2-7 concrete subtasks that can be \
executed independently or in dependency order.

For each subtask, assign the best Atlas model:
- atlas-plan: planning, coordination, writing briefs
- atlas-code: code generation, debugging, code review
- atlas-secure: security analysis, threat modeling
- atlas-infra: infrastructure, DevOps, deployment
- atlas-data: data analysis, SQL, statistics
- atlas-books: documentation, writing, research
- atlas-audit: compliance, log analysis, structured extraction

Return ONLY valid JSON (no markdown fences), an array of objects:
[
  {"id": 0, "task": "description", "atlas_model": "atlas-code", "dependencies": []},
  {"id": 1, "task": "description", "atlas_model": "atlas-data", "dependencies": [0]}
]

dependencies is a list of subtask ids that must complete before this one starts.
Keep it practical — no more than {max_depth} levels of dependency depth.

USER GOAL: {goal}
"""


@dataclass
class SubtaskResult:
    id: int
    task: str
    atlas_model: str
    status: str = "pending"  # pending | running | completed | failed
    result: str | None = None
    error: str | None = None
    latency_ms: int = 0


class PlanningEngine:
    def __init__(self):
        self.max_depth: int = settings.planning_max_depth
        self.max_workers: int = settings.planning_max_workers

    async def create_plan(
        self,
        workspace_id: str,
        goal: str,
        created_by: str | None = None,
    ) -> str:
        """Decompose a goal into subtasks using atlas-plan and persist as TaskPlan.

        Returns the plan UUID.
        """
        plan_id = uuid.uuid4()

        # Decompose via atlas-plan
        subtasks = await self._decompose(goal)

        # Persist
        from a1.db.engine import async_session
        from a1.db.models import TaskPlan

        async with async_session() as session:
            async with session.begin():
                plan = TaskPlan(
                    id=plan_id,
                    workspace_id=uuid.UUID(workspace_id),
                    root_task=goal,
                    decomposed=subtasks,
                    status="planning",
                    steps_total=len(subtasks),
                    created_by=created_by,
                )
                session.add(plan)

        log.info(f"[planner] Created plan {plan_id} with {len(subtasks)} subtasks for: {goal[:80]}")
        return str(plan_id)

    async def execute_plan(self, plan_id: str) -> str | None:
        """Execute all subtasks in dependency order.

        Returns the final synthesized result, or None on failure.
        """
        from sqlalchemy import select

        from a1.db.engine import async_session
        from a1.db.models import TaskPlan

        # Load plan
        async with async_session() as session:
            result = await session.execute(
                select(TaskPlan).where(TaskPlan.id == uuid.UUID(plan_id))
            )
            plan = result.scalar_one_or_none()
            if not plan:
                log.error(f"[planner] Plan {plan_id} not found")
                return None

            subtasks_raw = plan.decomposed if isinstance(plan.decomposed, list) else []
            goal = plan.root_task

        # Build subtask objects
        subtasks = [
            SubtaskResult(
                id=s.get("id", i),
                task=s.get("task", ""),
                atlas_model=s.get("atlas_model", "atlas-plan"),
            )
            for i, s in enumerate(subtasks_raw)
        ]
        deps_map: dict[int, list[int]] = {
            s.get("id", i): s.get("dependencies", []) for i, s in enumerate(subtasks_raw)
        }

        # Update status to executing
        await self._update_plan_status(plan_id, "executing")

        # Execute in waves (topological order by dependencies)
        completed_ids: set[int] = set()
        results_map: dict[int, str] = {}

        for wave in range(self.max_depth + 2):  # safety cap
            # Find ready subtasks (all deps completed)
            ready = [
                st
                for st in subtasks
                if st.status == "pending"
                and all(d in completed_ids for d in deps_map.get(st.id, []))
            ]
            if not ready:
                if all(st.status in ("completed", "failed") for st in subtasks):
                    break
                # Stuck — remaining subtasks have unmet deps
                log.warning(f"[planner] Plan {plan_id} stuck at wave {wave}, breaking")
                break

            # Execute ready subtasks in parallel (capped)
            batch = ready[: self.max_workers]
            log.info(f"[planner] Plan {plan_id} wave {wave}: executing {len(batch)} subtasks")

            tasks = [self._execute_subtask(st, results_map) for st in batch]
            await asyncio.gather(*tasks, return_exceptions=True)

            for st in batch:
                if st.status == "completed":
                    completed_ids.add(st.id)
                    results_map[st.id] = st.result or ""

            # Update progress
            steps_done = sum(1 for st in subtasks if st.status == "completed")
            await self._update_plan_progress(plan_id, steps_done)

        # Synthesize final result from all subtask results
        all_failed = all(st.status == "failed" for st in subtasks)
        if all_failed:
            await self._update_plan_status(plan_id, "failed")
            return None

        final_result = await self._synthesize(goal, subtasks, results_map)

        # Persist final result
        from a1.db.engine import async_session as _as

        async with _as() as session:
            async with session.begin():
                from sqlalchemy import update

                await session.execute(
                    update(TaskPlan)
                    .where(TaskPlan.id == uuid.UUID(plan_id))
                    .values(
                        status="completed",
                        result=final_result,
                        steps_completed=sum(1 for st in subtasks if st.status == "completed"),
                        completed_at=now_ist(),
                    )
                )

        log.info(
            f"[planner] Plan {plan_id} completed — "
            f"{len(completed_ids)}/{len(subtasks)} subtasks succeeded"
        )
        return final_result

    async def _decompose(self, goal: str) -> list[dict]:
        """Ask atlas-plan to decompose the goal into subtasks."""
        from fastapi import Response

        from a1.proxy.request_models import ChatCompletionRequest, MessageInput
        from a1.training.auto_trainer import handle_dual_execution

        prompt = _DECOMPOSE_PROMPT.format(goal=goal, max_depth=self.max_depth)
        req = ChatCompletionRequest(
            model="atlas-plan",
            messages=[
                MessageInput(
                    role="system",
                    content="You are a task decomposition engine. Return only valid JSON.",
                ),
                MessageInput(role="user", content=prompt),
            ],
            max_tokens=2000,
            temperature=0.3,
        )

        result = await handle_dual_execution(req, Response(), "chat", 0.9, atlas_model="atlas-plan")
        if not result or not result.choices:
            log.warning("[planner] Decomposition failed, returning single-step plan")
            return [{"id": 0, "task": goal, "atlas_model": "atlas-plan", "dependencies": []}]

        text = result.choices[0].message.content or ""
        try:
            # Strip markdown fences if present
            text = text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()
            subtasks = json.loads(text)
            if isinstance(subtasks, list) and subtasks:
                return subtasks
        except (json.JSONDecodeError, TypeError) as e:
            log.warning(f"[planner] Failed to parse decomposition JSON: {e}")

        return [{"id": 0, "task": goal, "atlas_model": "atlas-plan", "dependencies": []}]

    async def _execute_subtask(
        self,
        subtask: SubtaskResult,
        prior_results: dict[int, str],
    ) -> None:
        """Execute a single subtask via the distillation pipeline."""
        subtask.status = "running"
        start = time.time()

        try:
            from fastapi import Response

            from a1.proxy.request_models import ChatCompletionRequest, MessageInput
            from a1.training.auto_trainer import handle_dual_execution

            # Build context from prior subtask results
            context_parts = []
            if prior_results:
                context_parts.append("Context from prior steps:")
                for sid, res in prior_results.items():
                    context_parts.append(f"  Step {sid}: {res[:500]}")

            messages = [
                MessageInput(
                    role="system",
                    content="You are Atlas by Alpheric.AI. Complete this subtask concisely.",
                ),
            ]
            if context_parts:
                messages.append(MessageInput(role="user", content="\n".join(context_parts)))
            messages.append(MessageInput(role="user", content=subtask.task))

            req = ChatCompletionRequest(
                model=subtask.atlas_model,
                messages=messages,
                max_tokens=1500,
            )

            result = await asyncio.wait_for(
                handle_dual_execution(
                    req, Response(), "chat", 0.9, atlas_model=subtask.atlas_model
                ),
                timeout=settings.agent_execution_timeout,
            )

            if result and result.choices:
                subtask.result = result.choices[0].message.content
                subtask.status = "completed"
            else:
                subtask.status = "failed"
                subtask.error = "No response from provider"

        except asyncio.TimeoutError:
            subtask.status = "failed"
            subtask.error = f"Timeout after {settings.agent_execution_timeout}s"
        except Exception as e:
            subtask.status = "failed"
            subtask.error = str(e)

        subtask.latency_ms = int((time.time() - start) * 1000)
        log.info(
            f"[planner] Subtask {subtask.id} ({subtask.atlas_model}): "
            f"{subtask.status} in {subtask.latency_ms}ms"
        )

    async def _synthesize(
        self,
        goal: str,
        subtasks: list[SubtaskResult],
        results_map: dict[int, str],
    ) -> str:
        """Synthesize final answer from all subtask results."""
        parts = [f"Goal: {goal}\n"]
        for st in subtasks:
            status_icon = "done" if st.status == "completed" else "failed"
            result_text = results_map.get(st.id, st.error or "no output")
            parts.append(f"[{status_icon}] Step {st.id} ({st.atlas_model}): {st.task}")
            parts.append(f"  Result: {result_text[:1000]}\n")

        # Ask atlas-plan to produce a coherent summary
        from fastapi import Response

        from a1.proxy.request_models import ChatCompletionRequest, MessageInput
        from a1.training.auto_trainer import handle_dual_execution

        synthesis_prompt = (
            "Synthesize these subtask results into a clear, actionable final answer.\n\n"
            + "\n".join(parts)
        )

        req = ChatCompletionRequest(
            model="atlas-plan",
            messages=[
                MessageInput(
                    role="system",
                    content=(
                        "You are Atlas by Alpheric.AI. "
                        "Synthesize subtask results into a coherent answer."
                    ),
                ),
                MessageInput(role="user", content=synthesis_prompt),
            ],
            max_tokens=2000,
        )

        result = await handle_dual_execution(req, Response(), "chat", 0.9, atlas_model="atlas-plan")
        if result and result.choices:
            return result.choices[0].message.content or "\n".join(parts)

        # Fallback: concatenate
        return "\n".join(parts)

    async def _update_plan_status(self, plan_id: str, status: str):
        from sqlalchemy import update

        from a1.db.engine import async_session
        from a1.db.models import TaskPlan

        async with async_session() as session:
            async with session.begin():
                await session.execute(
                    update(TaskPlan).where(TaskPlan.id == uuid.UUID(plan_id)).values(status=status)
                )

    async def _update_plan_progress(self, plan_id: str, steps_done: int):
        from sqlalchemy import update

        from a1.db.engine import async_session
        from a1.db.models import TaskPlan

        async with async_session() as session:
            async with session.begin():
                await session.execute(
                    update(TaskPlan)
                    .where(TaskPlan.id == uuid.UUID(plan_id))
                    .values(steps_completed=steps_done)
                )


# Singleton
planning_engine = PlanningEngine()
