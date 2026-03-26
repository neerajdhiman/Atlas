import pytest


@pytest.fixture
def sample_messages():
    return [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Write a Python function to sort a list"},
    ]


@pytest.fixture
def sample_chat_request():
    return {
        "model": "auto",
        "messages": [
            {"role": "user", "content": "Hello, how are you?"},
        ],
    }
