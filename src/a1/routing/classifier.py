"""Task type classifier. Starts rule-based, upgrades to ML when enough data exists."""

from a1.proxy.request_models import ChatCompletionRequest
from a1.routing.features import extract_features


TASK_TYPES = [
    "code", "chat", "analysis", "creative", "summarization",
    "translation", "math", "structured_extraction", "general",
]


def classify_task(request: ChatCompletionRequest) -> tuple[str, float]:
    """Classify the task type. Returns (task_type, confidence)."""
    features = extract_features(request)

    # Rule-based classification (Tier 1)
    # Priority order matters — more specific patterns first

    if features.has_tools and features.has_code_markers:
        return "code", 0.9

    # Only classify as code if user message (not system prompt) has code markers
    # and the message is medium+ length — short messages with code keywords are likely chat
    if features.has_code_markers and features.token_count_bucket in ("medium", "long", "very_long"):
        return "code", 0.85

    if features.has_code_markers and features.token_count_bucket == "short":
        return "chat", 0.6  # short messages with code words → likely casual chat

    if features.has_math_markers:
        return "math", 0.8

    if features.has_translation_cues:
        return "translation", 0.85

    if features.has_summarization_cues:
        return "summarization", 0.8

    if features.has_structured_output_cues:
        return "structured_extraction", 0.75

    if features.has_tools:
        return "code", 0.6  # tool use often implies agentic/code tasks

    if features.token_count_bucket == "very_long" and features.has_system_prompt:
        return "analysis", 0.6

    if features.token_count_bucket == "short" and not features.has_system_prompt:
        return "chat", 0.7

    if features.has_question_markers and features.token_count_bucket in ("short", "medium"):
        return "chat", 0.65

    return "general", 0.5
