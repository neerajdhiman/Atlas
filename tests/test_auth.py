"""Tests for auth middleware: AuthContext, workspace binding, rate limiting."""

import pytest

from a1.common.auth import (
    AuthContext,
    _enforce_rate_limit_memory,
    _mem_buckets,
    hash_key,
)


class TestHashKey:
    def test_deterministic(self):
        assert hash_key("test") == hash_key("test")

    def test_different_keys_different_hashes(self):
        assert hash_key("key1") != hash_key("key2")

    def test_returns_hex_string(self):
        h = hash_key("test")
        assert len(h) == 64  # SHA256 hex
        assert all(c in "0123456789abcdef" for c in h)


class TestAuthContext:
    def test_dev_mode(self):
        ctx = AuthContext(api_key="dev", key_hash=None, workspace_id=None, role="admin")
        assert ctx.role == "admin"
        assert ctx.workspace_id is None

    def test_workspace_bound(self):
        ctx = AuthContext(
            api_key="sk-test",
            key_hash="abc123",
            workspace_id="ws-001",
            role="developer",
        )
        assert ctx.workspace_id == "ws-001"
        assert ctx.role == "developer"


class TestInMemoryRateLimiter:
    def setup_method(self):
        _mem_buckets.clear()

    def test_allows_within_limit(self):
        # Should not raise for first request
        _enforce_rate_limit_memory("test-key", 60)

    def test_blocks_over_limit(self):
        # Fill the bucket
        for _ in range(60):
            _enforce_rate_limit_memory("test-key-2", 60)
        # 61st should fail
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            _enforce_rate_limit_memory("test-key-2", 60)
        assert exc.value.status_code == 429
        assert "Rate limit exceeded" in exc.value.detail

    def test_separate_keys_separate_limits(self):
        for _ in range(60):
            _enforce_rate_limit_memory("key-a", 60)
        # key-b should still work
        _enforce_rate_limit_memory("key-b", 60)
