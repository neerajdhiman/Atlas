from pydantic import BaseModel, Field


class FunctionDef(BaseModel):
    name: str
    description: str | None = None
    parameters: dict | None = None


class ToolDef(BaseModel):
    type: str = "function"
    function: FunctionDef


class MessageInput(BaseModel):
    role: str
    content: str | None = None
    name: str | None = None
    tool_calls: list[dict] | None = None
    tool_call_id: str | None = None


class ChatCompletionRequest(BaseModel):
    model: str = "auto"
    messages: list[MessageInput]
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    stream: bool = False
    tools: list[ToolDef] | None = None
    tool_choice: str | dict | None = None
    stop: str | list[str] | None = None
    presence_penalty: float | None = None
    frequency_penalty: float | None = None
    n: int | None = 1
    user: str | None = None

    # A1 extensions
    strategy: str | None = None  # best_quality, lowest_cost, lowest_latency
    conversation_id: str | None = None
    session_id: str | None = None
    previous_response_id: str | None = None
