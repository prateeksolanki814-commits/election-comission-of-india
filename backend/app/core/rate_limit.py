"""
Sliding-window rate limiter backed by Redis. Used for:
  - login attempts per voter_code_hash and per ip_hash
  - ballot submission attempts per ip_hash (token itself is single-use so
    this is a secondary defense, not the primary duplicate-vote control)

Uses a simple fixed-window counter with TTL — sufficient for demo scale and
easy to reason about; documented as swappable for a token-bucket or
sliding-log algorithm in a production deployment.
"""
import redis.asyncio as redis

from app.core.config import get_settings

settings = get_settings()
_redis_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


class RateLimitExceeded(Exception):
    def __init__(self, retry_after_seconds: int):
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"Rate limit exceeded, retry after {retry_after_seconds}s")


async def check_rate_limit(key: str, max_attempts: int, window_seconds: int) -> None:
    """Raises RateLimitExceeded if the caller has exceeded max_attempts
    within window_seconds. `key` should already be a hashed/opaque
    identifier — never a raw voter code or plaintext IP."""
    r = get_redis()
    redis_key = f"ratelimit:{key}"
    current = await r.incr(redis_key)
    if current == 1:
        await r.expire(redis_key, window_seconds)
    if current > max_attempts:
        ttl = await r.ttl(redis_key)
        raise RateLimitExceeded(retry_after_seconds=max(ttl, 1))
