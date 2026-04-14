"""Pydantic request/response schemas for admin dashboard endpoints.

Replaces raw dict inputs with typed, validated models.
"""

from pydantic import BaseModel, Field

# --- Agents ---


class CreateAgentRequest(BaseModel):
    workspace_id: str
    name: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=256)
    atlas_model: str = "atlas-plan"
    system_prompt: str | None = None
    tools: list[str] = []
    memory_config: dict = Field(default_factory=lambda: {"type": "sliding_window", "limit": 20})
    parent_id: str | None = None
    app_id: str | None = None
    metadata: dict = Field(default_factory=dict)
    created_by: str | None = None


class UpdateAgentRequest(BaseModel):
    display_name: str | None = None
    atlas_model: str | None = None
    system_prompt: str | None = None
    tools: list[str] | None = None
    memory_config: dict | None = None
    status: str | None = None
    metadata: dict | None = None


class RunAgentRequest(BaseModel):
    task: str = Field(min_length=1)
    messages: list[dict] | None = None
    max_tokens: int = 2000


# --- Applications ---


class CreateApplicationRequest(BaseModel):
    workspace_id: str
    name: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=256)
    atlas_model: str = "atlas-plan"
    system_prompt: str | None = None
    tools: list[str] = []
    agent_pool: list[str] = []
    rate_limit_rpm: int = 60
    settings: dict = Field(default_factory=dict)
    created_by: str | None = None


class UpdateApplicationRequest(BaseModel):
    display_name: str | None = None
    atlas_model: str | None = None
    system_prompt: str | None = None
    tools: list[str] | None = None
    agent_pool: list[str] | None = None
    rate_limit_rpm: int | None = None


# --- Workspaces ---


class CreateWorkspaceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    slug: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9-]+$")
    settings: dict = Field(default_factory=dict)


# --- Plans ---


class CreatePlanRequest(BaseModel):
    workspace_id: str
    goal: str = Field(min_length=1)
    created_by: str | None = None


# --- Training ---


class CreateTrainingRunRequest(BaseModel):
    base_model: str
    task_type: str
    dataset_size: int | None = None
    config: dict = Field(default_factory=dict)


# --- Feedback ---


class AddFeedbackRequest(BaseModel):
    signal_type: str = "thumbs"
    value: float = Field(ge=0.0, le=5.0)
    evaluator: str | None = None
