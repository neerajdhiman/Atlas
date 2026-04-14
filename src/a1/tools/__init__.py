"""Tool registry — exposes computer use and custom tools for agents."""

from a1.common.logging import get_logger

log = get_logger("tools")

# Global tool registry: name → callable async function(args) → str
_tools: dict[str, "ToolDefinition"] = {}


class ToolDefinition:
    def __init__(self, name: str, description: str, handler, parameters: dict | None = None):
        self.name = name
        self.description = description
        self.handler = handler  # async (args: dict) -> str
        self.parameters = parameters or {}


def register_tool(defn: ToolDefinition):
    _tools[defn.name] = defn
    log.debug(f"Registered tool: {defn.name}")


def get_tool(name: str) -> ToolDefinition | None:
    return _tools.get(name)


def list_tools() -> list[dict]:
    return [
        {"name": t.name, "description": t.description, "parameters": t.parameters}
        for t in _tools.values()
    ]


async def execute_tool(name: str, args: dict) -> str:
    tool = _tools.get(name)
    if not tool:
        return f"Error: unknown tool '{name}'"
    try:
        return await tool.handler(args)
    except Exception as e:
        return f"Error executing {name}: {e}"
