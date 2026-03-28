"""Extract lightweight features from incoming requests for task classification."""

import re
from dataclasses import dataclass

from a1.common.tokens import count_tokens
from a1.proxy.request_models import ChatCompletionRequest


@dataclass
class RequestFeatures:
    token_count_bucket: str  # short, medium, long, very_long
    has_system_prompt: bool
    has_tools: bool
    has_code_markers: bool
    has_question_markers: bool
    has_translation_cues: bool
    has_summarization_cues: bool
    has_math_markers: bool
    has_structured_output_cues: bool
    conversation_turns: int
    max_tokens_bucket: str  # low, medium, high, unlimited


CODE_PATTERNS = re.compile(
    r'```|def\s+\w+|function\s+\w+|class\s+\w+|import\s+\w+|from\s+\w+|#include|'
    r'console\.log|System\.out|print\(|return\s+|if\s*\(|for\s*\(|while\s*\('
)
QUESTION_PATTERNS = re.compile(r'\?\s*$|^(what|how|why|when|where|who|which|can|could|should|is|are|do|does)\b', re.IGNORECASE | re.MULTILINE)
TRANSLATION_CUES = re.compile(r'translat|convert.*language|in (english|spanish|french|german|chinese|japanese|korean|hindi)', re.IGNORECASE)
SUMMARIZATION_CUES = re.compile(r'summar|tl;?dr|brief|condense|key points|overview of', re.IGNORECASE)
MATH_PATTERNS = re.compile(r'calculat|equation|formula|integral|derivative|solve|matrix|algebra|statistic|probability|\d+\s*[\+\-\*\/\^]\s*\d+', re.IGNORECASE)
STRUCTURED_CUES = re.compile(r'json|xml|csv|yaml|schema|structured|format.*output|extract.*from', re.IGNORECASE)


def _token_bucket(count: int) -> str:
    if count < 100:
        return "short"
    elif count < 500:
        return "medium"
    elif count < 2000:
        return "long"
    return "very_long"


def _max_tokens_bucket(max_tokens: int | None) -> str:
    if max_tokens is None:
        return "unlimited"
    if max_tokens < 256:
        return "low"
    elif max_tokens < 1024:
        return "medium"
    return "high"


def extract_features(request: ChatCompletionRequest) -> RequestFeatures:
    """Extract features from a chat completion request. Must be fast (<1ms)."""
    full_text = " ".join(m.content or "" for m in request.messages)
    token_count = count_tokens(full_text)

    has_system = any(m.role == "system" for m in request.messages)
    user_turns = sum(1 for m in request.messages if m.role == "user")

    return RequestFeatures(
        token_count_bucket=_token_bucket(token_count),
        has_system_prompt=has_system,
        has_tools=bool(request.tools),
        has_code_markers=bool(CODE_PATTERNS.search(full_text)),
        has_question_markers=bool(QUESTION_PATTERNS.search(full_text)),
        has_translation_cues=bool(TRANSLATION_CUES.search(full_text)),
        has_summarization_cues=bool(SUMMARIZATION_CUES.search(full_text)),
        has_math_markers=bool(MATH_PATTERNS.search(full_text)),
        has_structured_output_cues=bool(STRUCTURED_CUES.search(full_text)),
        conversation_turns=user_turns,
        max_tokens_bucket=_max_tokens_bucket(request.max_tokens),
    )
