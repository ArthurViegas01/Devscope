"""Daily LLM call budget enforced via a Redis counter.

Fail-closed: if Redis is unavailable, consume() returns False and callers
must reject the request. This prevents unbounded Groq spend during an
Upstash outage (the same scenario where the per-IP rate limiter also fails).
"""

from __future__ import annotations

from datetime import date

import redis.asyncio as redis

from devscope.logging_config import get_logger

log = get_logger(__name__)


class LLMBudget:
    """Atomic daily counter backed by Redis. Thread-safe via INCR atomicity."""

    def __init__(self, redis_client: redis.Redis, daily_cap: int) -> None:
        self._redis = redis_client
        self._cap = daily_cap

    async def consume(self) -> bool:
        """Increment counter. Returns True if within budget, False to reject."""
        key = f"llm:budget:{date.today().isoformat()}"
        try:
            n = await self._redis.incr(key)
            if n == 1:
                await self._redis.expire(key, 86400)
            if n > self._cap:
                log.warning("llm_budget.exceeded", count=n, cap=self._cap)
                return False
            return True
        except Exception:  # noqa: BLE001
            log.warning("llm_budget.redis_error")
            return False
