import tiktoken

_encoder = None


def get_encoder():
    global _encoder
    if _encoder is None:
        _encoder = tiktoken.get_encoding("cl100k_base")
    return _encoder


def count_tokens(text: str) -> int:
    return len(get_encoder().encode(text))


def count_messages_tokens(messages: list[dict]) -> int:
    total = 0
    for msg in messages:
        total += 4  # message overhead
        total += count_tokens(msg.get("content", ""))
        if msg.get("role"):
            total += 1
    total += 2  # reply priming
    return total
