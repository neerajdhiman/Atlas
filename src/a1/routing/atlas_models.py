"""Atlas model family definitions and routing metadata — single source of truth."""

# Maps Atlas model name → task type (used to skip classifier when model is explicit)
ATLAS_TASK_MAP: dict[str, str] = {
    "atlas-plan": "chat",
    "atlas-code": "code",
    "atlas-secure": "analysis",
    "atlas-infra": "infra",
    "atlas-data": "analysis",
    "atlas-books": "creative",
    "atlas-audit": "structured_extraction",
}

# Maps task type → best Atlas model (for auto-selection in /atlas endpoint)
TASK_TO_ATLAS: dict[str, str] = {
    "chat": "atlas-plan",
    "general": "atlas-plan",
    "code": "atlas-code",
    "structured_extraction": "atlas-audit",
    "analysis": "atlas-secure",
    "math": "atlas-data",
    "creative": "atlas-books",
    "summarization": "atlas-books",
    "translation": "atlas-books",
}

# Full routing metadata per Atlas model — used by /atlas endpoint and /atlas/models
ATLAS_TASK_ROUTING: dict[str, dict] = {
    "atlas-plan": {"tasks": ["chat", "general", "creative"], "description": "Planning, discussion, brainstorming"},
    "atlas-code": {"tasks": ["code", "structured_extraction"], "description": "Code generation, debugging, review"},
    "atlas-secure": {"tasks": ["analysis", "math"], "description": "Security analysis, reasoning, auditing"},
    "atlas-infra": {"tasks": ["infra"], "description": "Infrastructure, DevOps, deployment"},
    "atlas-data": {"tasks": ["analysis", "summarization", "math"], "description": "Data analysis, statistics, ETL"},
    "atlas-books": {"tasks": ["creative", "summarization", "translation"], "description": "Documentation, writing, research"},
    "atlas-audit": {"tasks": ["structured_extraction", "analysis"], "description": "Compliance auditing, log analysis"},
}


def resolve_atlas_model(task_type: str) -> str:
    """Pick the best Atlas model for a given task type."""
    return TASK_TO_ATLAS.get(task_type, "atlas-plan")
