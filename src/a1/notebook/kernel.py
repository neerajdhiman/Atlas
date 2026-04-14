"""Notebook kernel — executes cells in isolated subprocesses.

Supports three kernel types:
  - python: runs code via subprocess (30s timeout)
  - sql: runs SQL against the app's async DB engine
  - bash: runs shell commands via subprocess

After execution, optionally sends the cell code + output to the notebook's
atlas_model for AI explanation and suggestions.
"""

import asyncio
import sys
import tempfile
from pathlib import Path

from a1.common.logging import get_logger
from config.settings import settings

log = get_logger("notebook.kernel")

_CELL_TIMEOUT = 30  # seconds


async def execute_cell(
    source: str,
    kernel: str = "python",
    atlas_model: str = "atlas-code",
) -> dict:
    """Execute a notebook cell and return result dict.

    Returns:
        {"output": str, "ai_suggestion": str | None, "error": bool}
    """
    output = ""
    error = False

    try:
        if kernel == "python":
            output = await _run_python(source)
        elif kernel == "sql":
            output = await _run_sql(source)
        elif kernel == "bash":
            output = await _run_bash(source)
        else:
            output = f"Unsupported kernel: {kernel}"
            error = True
    except asyncio.TimeoutError:
        output = f"Execution timed out after {_CELL_TIMEOUT}s"
        error = True
    except Exception as e:
        output = f"Error: {e}"
        error = True

    # Get AI suggestion (non-blocking, best-effort)
    ai_suggestion = None
    if not error and settings.distillation_enabled:
        try:
            ai_suggestion = await asyncio.wait_for(
                _get_ai_suggestion(source, output, kernel, atlas_model),
                timeout=30,
            )
        except Exception as e:
            log.debug(f"AI suggestion failed: {e}")

    return {
        "output": output[:8192],
        "ai_suggestion": ai_suggestion[:4096] if ai_suggestion else None,
        "error": error,
    }


async def _run_python(source: str) -> str:
    """Execute Python code in a subprocess."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(source)
        f.flush()
        path = f.name

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=tempfile.gettempdir(),
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=_CELL_TIMEOUT)
        return stdout.decode("utf-8", errors="replace")[:8192]
    finally:
        Path(path).unlink(missing_ok=True)


async def _run_sql(source: str) -> str:
    """Execute SQL against the app database."""
    from sqlalchemy import text

    from a1.db.engine import async_session

    async with async_session() as session:
        result = await session.execute(text(source))
        try:
            rows = result.fetchall()
            if not rows:
                return "(no rows returned)"
            cols = result.keys()
            lines = ["\t".join(str(c) for c in cols)]
            for row in rows[:100]:
                lines.append("\t".join(str(v) for v in row))
            if len(rows) > 100:
                lines.append(f"... ({len(rows)} total rows, showing first 100)")
            return "\n".join(lines)
        except Exception:
            return f"Statement executed ({result.rowcount} rows affected)"


async def _run_bash(source: str) -> str:
    """Execute bash commands in a subprocess."""
    proc = await asyncio.create_subprocess_shell(
        source,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=tempfile.gettempdir(),
    )
    stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=_CELL_TIMEOUT)
    return stdout.decode("utf-8", errors="replace")[:8192]


async def _get_ai_suggestion(
    source: str,
    output: str,
    kernel: str,
    atlas_model: str,
) -> str | None:
    """Ask Atlas to explain the output and suggest improvements."""
    from fastapi import Response

    from a1.proxy.request_models import ChatCompletionRequest, MessageInput
    from a1.training.auto_trainer import handle_dual_execution

    prompt = (
        f"A user ran this {kernel} cell:\n```\n{source[:2000]}\n```\n\n"
        f"Output:\n```\n{output[:2000]}\n```\n\n"
        "Briefly explain the output and suggest any improvements or next steps."
    )

    req = ChatCompletionRequest(
        model=atlas_model,
        messages=[
            MessageInput(
                role="system",
                content="You are Atlas by Alpheric.AI. Help the user understand their code output.",
            ),
            MessageInput(role="user", content=prompt),
        ],
        max_tokens=500,
        temperature=0.3,
    )

    result = await handle_dual_execution(req, Response(), "code", 0.9, atlas_model=atlas_model)
    if result and result.choices:
        return result.choices[0].message.content
    return None
