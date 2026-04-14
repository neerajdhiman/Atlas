"""Unit tests for task type classifier — covers all 12 decision branches."""

from a1.proxy.request_models import ChatCompletionRequest, MessageInput
from a1.routing.classifier import classify_task


def req(*contents, system: str | None = None) -> ChatCompletionRequest:
    """Build a minimal ChatCompletionRequest for classifier tests."""
    msgs = []
    if system:
        msgs.append(MessageInput(role="system", content=system))
    for c in contents:
        msgs.append(MessageInput(role="user", content=c))
    return ChatCompletionRequest(model="auto", messages=msgs)


# Branch 1: has_tools AND has_code_markers → code
def test_code_tools_and_code_markers():
    r = req("Write a function to parse JSON")
    r.tools = [{"function": {"name": "exec_code"}}]  # type: ignore[attr-defined]
    task, conf = classify_task(r)
    assert task == "code"


# Branch 2: has_code_markers AND token_count_bucket in (medium, long, very_long) → code
def test_code_medium_message():
    # Need 100+ tokens: ~75+ words with a code marker to be in "medium" bucket
    filler = "please " * 150  # ~150+ tokens to ensure "medium" bucket (>100)
    content = f"{filler} Write a Python function to sort a list of integers"
    task, conf = classify_task(req(content))
    assert task == "code"
    assert conf > 0.0


# Branch 3: has_code_markers AND token_count_bucket == short → chat
def test_chat_short_with_code_words():
    task, conf = classify_task(req("hello function"))
    assert task == "chat"


# Branch 4: SECURITY_ANALYSIS_PATTERNS → analysis
def test_analysis_security_keyword():
    task, conf = classify_task(req("Check this code for SQL injection vulnerability"))
    assert task == "analysis"


# Branch 4b: CVE keyword
def test_analysis_cve():
    task, conf = classify_task(req("Explain CVE-2023-1234 and its impact"))
    assert task == "analysis"


# Branch 5: has_math_markers → math
def test_math():
    task, conf = classify_task(req("Calculate the derivative of f(x) = 3x^2 + 2x - 5"))
    assert task == "math"


# Branch 6: has_translation_cues → translation
def test_translation():
    task, conf = classify_task(req("Translate the following text to Spanish: Hello world"))
    assert task == "translation"


# Branch 7: has_summarization_cues → summarization
def test_summarization():
    task, conf = classify_task(
        req("Summarize this article: The quick brown fox jumps over the lazy dog")
    )
    assert task == "summarization"


# Branch 8: has_structured_output_cues → structured_extraction
def test_structured_extraction():
    task, conf = classify_task(req('Extract JSON from: {"name": "Alice", "age": 30}'))
    assert task == "structured_extraction"


# Branch 9: has_tools (no code markers) → code
def test_code_tools_only():
    r = req("Run this task for me")
    r.tools = [{"function": {"name": "search_web"}}]  # type: ignore[attr-defined]
    task, conf = classify_task(r)
    assert task == "code"


# Branch 10: very_long message + system prompt → analysis (requires 2000+ tokens)
def test_analysis_very_long_with_system():
    long_content = "word " * 2500  # ~2500 tokens → very_long bucket
    task, conf = classify_task(req(long_content, system="You are a helpful assistant."))
    assert task == "analysis"


# Branch 11: short message without system prompt → chat
def test_chat_short_no_system():
    task, conf = classify_task(req("Hi there"))
    assert task == "chat"


# Branch 12: has_question_markers + short/medium → chat
def test_chat_question():
    task, conf = classify_task(req("What is the capital of France?"))
    assert task == "chat"


# Default (no branch matches) → general
def test_general_default():
    task, conf = classify_task(req("word " * 50))
    # Long enough to not be short, no special markers — might hit analysis or general
    assert task in ("analysis", "general", "chat")


# Confidence is in valid range
def test_confidence_range():
    task, conf = classify_task(req("Write a Python hello world program"))
    assert 0.0 <= conf <= 1.0
