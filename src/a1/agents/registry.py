"""Agent Registry — singleton that loads and caches agent definitions from DB.

Initialized at application startup alongside ProviderRegistry.
Agents are addressed by name (slug) or UUID. Each agent carries its
Atlas model, system prompt, tool manifest, and memory config.
"""

from dataclasses import dataclass, field

from a1.common.logging import get_logger

log = get_logger("agents.registry")


@dataclass
class AgentDefinition:
    id: str
    workspace_id: str
    name: str  # slug: "data-analyst-bot"
    display_name: str
    atlas_model: str
    system_prompt: str | None
    tools: list[str]  # tool name strings
    memory_config: dict  # {"type": "sliding_window", "limit": 20}
    parent_id: str | None
    app_id: str | None
    status: str  # "active" | "paused" | "terminated"
    metadata: dict = field(default_factory=dict)


class AgentRegistry:
    """In-memory cache of agent definitions loaded from DB.

    Refresh policy: full reload on startup, plus `invalidate(agent_id)`
    for targeted cache busts after create/update/delete operations.
    """

    def __init__(self):
        self._by_id: dict[str, AgentDefinition] = {}
        self._by_name: dict[str, AgentDefinition] = {}  # workspace_id:name → agent
        self._initialized = False

    async def initialize(self):
        """Load all active agents from DB into memory."""
        await self._reload()
        self._initialized = True
        log.info(f"AgentRegistry initialized — {len(self._by_id)} agents loaded")

    async def _reload(self):
        """Full reload from DB."""
        try:
            from sqlalchemy import select

            from a1.db.engine import async_session
            from a1.db.models import Agent

            async with async_session() as session:
                result = await session.execute(select(Agent).where(Agent.status != "terminated"))
                agents = result.scalars().all()

            self._by_id = {}
            self._by_name = {}
            for a in agents:
                defn = AgentDefinition(
                    id=str(a.id),
                    workspace_id=str(a.workspace_id),
                    name=a.name,
                    display_name=a.display_name,
                    atlas_model=a.atlas_model,
                    system_prompt=a.system_prompt,
                    tools=a.tools if isinstance(a.tools, list) else [],
                    memory_config=a.memory_config if isinstance(a.memory_config, dict) else {},
                    parent_id=str(a.parent_id) if a.parent_id else None,
                    app_id=str(a.app_id) if a.app_id else None,
                    status=a.status,
                    metadata=a.metadata_ if isinstance(a.metadata_, dict) else {},
                )
                self._by_id[defn.id] = defn
                key = f"{defn.workspace_id}:{defn.name}"
                self._by_name[key] = defn
        except Exception as e:
            log.warning(f"AgentRegistry reload failed (no agents cached): {e}")

    def get_by_id(self, agent_id: str) -> AgentDefinition | None:
        return self._by_id.get(str(agent_id))

    def get_by_name(self, workspace_id: str, name: str) -> AgentDefinition | None:
        return self._by_name.get(f"{workspace_id}:{name}")

    def list_agents(self, workspace_id: str | None = None) -> list[AgentDefinition]:
        agents = list(self._by_id.values())
        if workspace_id:
            agents = [a for a in agents if a.workspace_id == workspace_id]
        return agents

    async def invalidate(self, agent_id: str | None = None):
        """Bust cache. If agent_id given, remove just that entry then reload.
        Called after create/update/delete via admin API.
        """
        if agent_id:
            self._by_id.pop(str(agent_id), None)
        await self._reload()


# Singleton
agent_registry = AgentRegistry()
