"""Unit tests for the in-memory LRU cache (T053)."""

from __future__ import annotations

import pytest

from router.cache import (
    RequestCache,
    _hash_messages,
    configure,
    lookup,
    store,
    get_hit_rate,
    get_size,
    reset,
)
import router.cache as cache_mod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _msgs(text: str) -> list[dict]:
    return [{"role": "user", "content": text}]


@pytest.fixture(autouse=True)
def clean_cache():
    """Ensure module-level cache is reset before/after each test."""
    cache_mod._cache = None
    cache_mod._enabled = False
    yield
    cache_mod._cache = None
    cache_mod._enabled = False


# ---------------------------------------------------------------------------
# RequestCache class — core LRU behaviour
# ---------------------------------------------------------------------------

class TestRequestCacheHitMiss:
    def test_miss_returns_none(self):
        c = RequestCache()
        assert c.get(_msgs("hello")) is None

    def test_hit_returns_stored_response(self):
        c = RequestCache()
        msgs = _msgs("hello")
        c.set(msgs, "world")
        assert c.get(msgs) == "world"

    def test_miss_increments_miss_counter(self):
        c = RequestCache()
        c.get(_msgs("x"))
        assert c.misses == 1
        assert c.hits == 0

    def test_hit_increments_hit_counter(self):
        c = RequestCache()
        msgs = _msgs("hello")
        c.set(msgs, "response")
        c.get(msgs)
        assert c.hits == 1
        assert c.misses == 0

    def test_different_messages_are_different_keys(self):
        c = RequestCache()
        c.set(_msgs("question A"), "answer A")
        assert c.get(_msgs("question B")) is None

    def test_same_content_different_role_is_different_key(self):
        c = RequestCache()
        c.set([{"role": "user", "content": "hi"}], "response")
        assert c.get([{"role": "assistant", "content": "hi"}]) is None

    def test_multi_message_conversation_keyed_correctly(self):
        c = RequestCache()
        msgs = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "What is 2+2?"},
        ]
        c.set(msgs, "4")
        assert c.get(msgs) == "4"
        # Subset of messages is a different key
        assert c.get([msgs[1]]) is None


class TestRequestCacheEviction:
    def test_evicts_lru_when_over_capacity(self):
        c = RequestCache(max_entries=3)
        c.set(_msgs("a"), "A")
        c.set(_msgs("b"), "B")
        c.set(_msgs("c"), "C")
        # Access 'a' to make it recently used
        c.get(_msgs("a"))
        # Add 'd' — 'b' should be evicted (LRU)
        c.set(_msgs("d"), "D")
        assert c.get(_msgs("b")) is None  # evicted
        assert c.get(_msgs("a")) == "A"   # still present (recently used)
        assert c.get(_msgs("c")) == "C"
        assert c.get(_msgs("d")) == "D"

    def test_size_does_not_exceed_max_entries(self):
        c = RequestCache(max_entries=5)
        for i in range(10):
            c.set(_msgs(f"msg {i}"), f"resp {i}")
        assert c.size() <= 5

    def test_overwrite_existing_key_does_not_grow_cache(self):
        c = RequestCache(max_entries=3)
        c.set(_msgs("a"), "A1")
        c.set(_msgs("a"), "A2")  # overwrite
        assert c.size() == 1
        assert c.get(_msgs("a")) == "A2"


class TestRequestCacheHitRate:
    def test_hit_rate_zero_with_no_requests(self):
        c = RequestCache()
        assert c.hit_rate() == 0.0

    def test_hit_rate_all_hits(self):
        c = RequestCache()
        c.set(_msgs("q"), "r")
        c.get(_msgs("q"))
        c.get(_msgs("q"))
        assert c.hit_rate() == 1.0

    def test_hit_rate_all_misses(self):
        c = RequestCache()
        c.get(_msgs("q1"))
        c.get(_msgs("q2"))
        assert c.hit_rate() == 0.0

    def test_hit_rate_mixed(self):
        c = RequestCache()
        c.set(_msgs("q"), "r")
        c.get(_msgs("q"))   # hit
        c.get(_msgs("x"))   # miss
        assert abs(c.hit_rate() - 0.5) < 1e-9

    def test_clear_resets_counters(self):
        c = RequestCache()
        c.set(_msgs("q"), "r")
        c.get(_msgs("q"))
        c.clear()
        assert c.hits == 0
        assert c.misses == 0
        assert c.size() == 0


# ---------------------------------------------------------------------------
# Module-level API — configure / lookup / store / toggle disable
# ---------------------------------------------------------------------------

class TestModuleLevelApi:
    def test_disabled_by_default(self):
        assert lookup(_msgs("hello")) is None

    def test_configure_enables_cache(self):
        configure(enabled=True, max_entries=100)
        assert cache_mod._enabled is True
        assert cache_mod._cache is not None

    def test_configure_disabled_leaves_cache_none(self):
        configure(enabled=False)
        assert cache_mod._enabled is False
        assert cache_mod._cache is None

    def test_lookup_miss_when_enabled_but_empty(self):
        configure(enabled=True)
        assert lookup(_msgs("anything")) is None

    def test_store_then_lookup_hit(self):
        configure(enabled=True)
        msgs = _msgs("What is 2+2?")
        store(msgs, "4")
        assert lookup(msgs) == "4"

    def test_store_noop_when_disabled(self):
        configure(enabled=False)
        store(_msgs("q"), "r")
        configure(enabled=True)
        assert lookup(_msgs("q")) is None  # was never stored

    def test_get_hit_rate_when_disabled(self):
        configure(enabled=False)
        assert get_hit_rate() == 0.0

    def test_get_size_when_disabled(self):
        configure(enabled=False)
        assert get_size() == 0

    def test_reset_clears_entries(self):
        configure(enabled=True)
        store(_msgs("q"), "r")
        assert get_size() == 1
        reset()
        assert get_size() == 0

    def test_lookup_noop_when_disabled_after_store(self):
        """Toggle: store while enabled, disable, then lookup → miss."""
        configure(enabled=True)
        msgs = _msgs("cached question")
        store(msgs, "cached answer")
        configure(enabled=False)
        assert lookup(msgs) is None

    def test_max_entries_respected(self):
        configure(enabled=True, max_entries=3)
        for i in range(5):
            store(_msgs(f"msg {i}"), f"resp {i}")
        assert get_size() <= 3


# ---------------------------------------------------------------------------
# Hash stability
# ---------------------------------------------------------------------------

class TestHashStability:
    def test_same_messages_same_hash(self):
        msgs = _msgs("hello world")
        assert _hash_messages(msgs) == _hash_messages(msgs)

    def test_different_messages_different_hash(self):
        assert _hash_messages(_msgs("a")) != _hash_messages(_msgs("b"))

    def test_hash_is_hex_string(self):
        h = _hash_messages(_msgs("test"))
        assert isinstance(h, str)
        assert len(h) == 64  # SHA-256 hex digest