"""In-memory LRU semantic cache keyed by exact request text hash."""

from __future__ import annotations

import hashlib
import json
import threading
from collections import OrderedDict
from typing import Optional


# ---------------------------------------------------------------------------
# Core cache class
# ---------------------------------------------------------------------------

class RequestCache:
    """
    LRU cache for routing responses.

    Keys are SHA-256 hashes of the normalized message content (exact match).
    When max_entries is reached, the least-recently-used entry is evicted.
    """

    def __init__(self, max_entries: int = 10_000) -> None:
        self._store: OrderedDict[str, str] = OrderedDict()
        self._lock = threading.Lock()
        self.max_entries = max_entries
        self.hits = 0
        self.misses = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, messages: list[dict]) -> Optional[str]:
        """Return cached response, or None on miss. Updates LRU order."""
        key = _hash_messages(messages)
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
                self.hits += 1
                return self._store[key]
            self.misses += 1
        return None

    def set(self, messages: list[dict], response: str) -> None:
        """Store a response. Evicts LRU entry when over capacity."""
        key = _hash_messages(messages)
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
            self._store[key] = response
            if len(self._store) > self.max_entries:
                self._store.popitem(last=False)  # remove least-recently-used

    def clear(self) -> None:
        """Reset the cache and counters."""
        with self._lock:
            self._store.clear()
            self.hits = 0
            self.misses = 0

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    def size(self) -> int:
        return len(self._store)


# ---------------------------------------------------------------------------
# Hash helper
# ---------------------------------------------------------------------------

def _hash_messages(messages: list[dict]) -> str:
    """Stable SHA-256 key from message role+content pairs (collision-resistant)."""
    canonical = json.dumps(
        [{"role": m.get("role", ""), "content": m.get("content", "")} for m in messages],
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


# ---------------------------------------------------------------------------
# Module-level singleton (T052: toggled via plugins.yaml)
# ---------------------------------------------------------------------------

_cache: Optional[RequestCache] = None
_enabled: bool = False
_module_lock = threading.Lock()


def configure(enabled: bool, max_entries: int = 10_000) -> None:
    """
    Configure the module-level cache from CacheConfig.
    Called by the pipeline when config is loaded.
    """
    global _cache, _enabled
    with _module_lock:
        _enabled = enabled
        _cache = RequestCache(max_entries=max_entries) if enabled else None


def lookup(messages: list[dict]) -> Optional[str]:
    """Return a cached response string, or None if disabled / cache miss."""
    if not _enabled or _cache is None:
        return None
    return _cache.get(messages)


def store(messages: list[dict], response: str) -> None:
    """Persist a response in the cache (no-op if disabled)."""
    if _enabled and _cache is not None:
        _cache.set(messages, response)


def get_hit_rate() -> float:
    """Current hit rate (0.0 if disabled or no requests yet)."""
    return _cache.hit_rate() if _cache is not None else 0.0


def get_size() -> int:
    """Number of entries currently in cache."""
    return _cache.size() if _cache is not None else 0


def reset() -> None:
    """Clear cache contents and counters — used in tests."""
    if _cache is not None:
        _cache.clear()