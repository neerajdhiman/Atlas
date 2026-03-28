"""Task type classifier. Starts rule-based, upgrades to ML when enough data exists."""

import re

from a1.proxy.request_models import ChatCompletionRequest
from a1.routing.features import RequestFeatures, extract_features


TASK_TYPES = [
    "code", "chat", "analysis", "creative", "summarization",
    "translation", "math", "structured_extraction", "general", "infra",
]

# P1: Security/data analysis keyword pattern — triggers analysis regardless of message length
SECURITY_ANALYSIS_PATTERNS = re.compile(
    r'vulnerability|CVE-\d|threat\s+model|audit|anomaly|dataset\b|data\s+leak|'
    r'pentest|sql\s+injection|xss|csrf|attack\s+surface|compliance\b|'
    r'intrusion|malware|exploit|breach|incident\s+response',
    re.IGNORECASE,
)


def _feature_confidence(features: RequestFeatures) -> float:
    """Compute confidence from feature match strength.

    Counts how many signal features are active and normalises to [0.4, 0.95].
    Replaces hardcoded constants so stored confidence values reflect real input signals.
    """
    active = sum([
        features.has_code_markers,
        features.has_tools,
        features.has_math_markers,
        features.has_translation_cues,
        features.has_summarization_cues,
        features.has_structured_output_cues,
        features.has_question_markers,
        features.has_system_prompt,
    ])
    total = 8
    # Scale: 0 active features → 0.4, all active → 0.95
    return round(0.4 + 0.55 * (active / total), 3)


def classify_task(request: ChatCompletionRequest) -> tuple[str, float]:
    """Classify the task type. Returns (task_type, confidence).

    Confidence is computed from feature match strength, not hardcoded constants,
    so stored routing_decisions values are usable as a scorer training signal.
    """
    features = extract_features(request)
    conf = _feature_confidence(features)

    # Rule-based classification (Tier 1)
    # Priority order matters — more specific patterns first

    if features.has_tools and features.has_code_markers:
        return "code", conf

    # Only classify as code if user message (not system prompt) has code markers
    # and the message is medium+ length — short messages with code keywords are likely chat
    if features.has_code_markers and features.token_count_bucket in ("medium", "long", "very_long"):
        return "code", conf

    if features.has_code_markers and features.token_count_bucket == "short":
        return "chat", conf  # short messages with code words → likely casual chat

    # P1: Security/data keywords → analysis regardless of message length.
    # Checked before math/translation/etc. because security terms take priority
    # (e.g. "CVE-2023-1234" falsely triggers math via the subtraction regex).
    full_text = " ".join(m.content or "" for m in request.messages)
    if SECURITY_ANALYSIS_PATTERNS.search(full_text):
        return "analysis", conf

    if features.has_math_markers:
        return "math", conf

    if features.has_translation_cues:
        return "translation", conf

    if features.has_summarization_cues:
        return "summarization", conf

    if features.has_structured_output_cues:
        return "structured_extraction", conf

    if features.has_tools:
        return "code", conf  # tool use often implies agentic/code tasks

    if features.token_count_bucket == "very_long" and features.has_system_prompt:
        return "analysis", conf

    if features.token_count_bucket == "short" and not features.has_system_prompt:
        return "chat", conf

    if features.has_question_markers and features.token_count_bucket in ("short", "medium"):
        return "chat", conf

    return "general", conf
