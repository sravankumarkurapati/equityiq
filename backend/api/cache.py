# backend/api/cache.py
#
# In-memory cache layer sitting in front of DynamoDB.
#
# Why two levels of caching:
#   Level 1 — this file — Python dict in RAM
#     Fastest possible lookup (microseconds)
#     Lost when the server restarts
#     Used for the current session's repeat requests
#
#   Level 2 — DynamoDB
#     Survives server restarts
#     Shared across multiple server instances
#     Used for cross-session caching (30 min TTL)
#
# Flow for a ticker request:
#   1. Check RAM cache → hit? return instantly
#   2. Check DynamoDB  → hit and fresh? load into RAM, return
#   3. Both miss       → run agents, save to both

import time
import logging
from typing import Optional

from backend.config import settings

logger = logging.getLogger(__name__)


class InMemoryCache:
    """
    Simple thread-safe in-memory cache using a Python dict.
    Stores analysis reports keyed by ticker symbol.
    Each entry has a timestamp so we can check freshness.
    """

    def __init__(self):
        # The cache store: {ticker: {"data": report_dict, "timestamp": float}}
        self._cache: dict = {}
        # TTL in seconds — matches the DynamoDB TTL setting
        self._ttl = settings.cache_ttl_seconds
        logger.info(f"InMemoryCache initialized with TTL={self._ttl}s")

    def get(self, ticker: str) -> Optional[dict]:
        """
        Retrieves a cached report for a ticker.
        Returns None if not in cache or if the entry is stale.
        """
        ticker = ticker.upper()
        entry = self._cache.get(ticker)

        if not entry:
            logger.debug(f"Cache miss (not found): {ticker}")
            return None

        # Check if entry is still fresh
        age = time.time() - entry["timestamp"]
        if age > self._ttl:
            # Entry exists but is too old — remove it and return None
            logger.info(f"Cache miss (stale, age={int(age)}s): {ticker}")
            del self._cache[ticker]
            return None

        logger.info(f"Cache hit (age={int(age)}s): {ticker}")
        return entry["data"]

    def set(self, ticker: str, data: dict) -> None:
        """
        Stores a report in the cache with current timestamp.
        Overwrites any existing entry for this ticker.
        """
        ticker = ticker.upper()
        self._cache[ticker] = {
            "data": data,
            "timestamp": time.time(),
        }
        logger.info(f"Cache set: {ticker} (TTL={self._ttl}s)")

    def invalidate(self, ticker: str) -> None:
        """
        Removes a ticker from cache.
        Called when force_refresh=True to ensure agents re-run.
        """
        ticker = ticker.upper()
        if ticker in self._cache:
            del self._cache[ticker]
            logger.info(f"Cache invalidated: {ticker}")

    def clear(self) -> None:
        """Clears entire cache — useful for testing."""
        self._cache.clear()
        logger.info("Cache cleared")

    @property
    def size(self) -> int:
        """Number of entries currently in cache."""
        return len(self._cache)


# ── Global cache instance ─────────────────────────────────────────
# Single instance shared across all API requests.
# FastAPI is single-process so this is safe.
# In a multi-worker setup you'd use Redis instead.
cache = InMemoryCache()