"""Token counting with per-model tokenizer selection.

Uses tiktoken for accurate token counting. Selects the appropriate
encoder based on the model family.
"""

import tiktoken

_encoders: dict[str, tiktoken.Encoding] = {}


def get_encoder(encoding_name: str = "cl100k_base") -> tiktoken.Encoding:
    if encoding_name not in _encoders:
        _encoders[encoding_name] = tiktoken.get_encoding(encoding_name)
    return _encoders[encoding_name]


def get_encoder_for_model(model: str) -> tiktoken.Encoding:
    """Select the best tiktoken encoder for a given model.

    - GPT-4o family → o200k_base
    - GPT-4, GPT-3.5, Claude family → cl100k_base
    - Ollama/local models → cl100k_base (within ~5% accuracy)
    """
    model_lower = model.lower()

    if any(model_lower.startswith(p) for p in ("gpt-4o", "chatgpt-4o", "o3", "o1")):
        return get_encoder("o200k_base")

    # cl100k_base works well for GPT-4, GPT-3.5, Claude, and is a
    # reasonable approximation for llama/mistral/deepseek families
    return get_encoder("cl100k_base")


def count_tokens(text: str) -> int:
    return len(get_encoder().encode(text))


def count_tokens_for_model(text: str, model: str) -> int:
    """Count tokens using the model-appropriate encoder."""
    return len(get_encoder_for_model(model).encode(text))


def count_messages_tokens(messages: list[dict]) -> int:
    return count_messages_tokens_for_model(messages, "cl100k_base")


def count_messages_tokens_for_model(messages: list[dict], model: str) -> int:
    """Count tokens in a messages array using the model-appropriate encoder."""
    encoder = get_encoder_for_model(model)
    total = 0
    for msg in messages:
        total += 4  # message overhead
        total += len(encoder.encode(msg.get("content", "")))
        if msg.get("role"):
            total += 1
    total += 2  # reply priming
    return total
