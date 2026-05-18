import redis.asyncio as aioredis
import time
from app.config import settings
from app.models.tenant import Tenant

redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)

class RateLimiter:
    """
    Token bucket rate limiter per tenant.
    Each tenant gets `requests_per_minute` tokens, refilled every 60s.
    """

    async def is_allowed(self, tenant: Tenant) -> tuple[bool, dict]:
        key = f"rate_limit:{tenant.id}"
        now = time.time()
        window = 60  # 1 minute window
        limit = tenant.requests_per_minute

        pipe = redis_client.pipeline()
        # Remove tokens older than the window
        pipe.zremrangebyscore(key, 0, now - window)
        # Count current tokens in window
        pipe.zcard(key)
        # Add current request timestamp
        pipe.zadd(key, {str(now): now})
        # Set expiry
        pipe.expire(key, window)
        results = await pipe.execute()

        current_count = results[1]

        if current_count >= limit:
            return False, {
                "allowed": False,
                "limit": limit,
                "current": current_count,
                "retry_after_seconds": window,
            }

        return True, {
            "allowed": True,
            "limit": limit,
            "current": current_count + 1,
            "remaining": limit - current_count - 1,
        }

    async def get_current_load(self, tenant_id: str) -> int:
        """Returns number of requests in last 60s for a tenant."""
        key = f"rate_limit:{tenant_id}"
        now = time.time()
        await redis_client.zremrangebyscore(key, 0, now - 60)
        return await redis_client.zcard(key)

rate_limiter = RateLimiter()