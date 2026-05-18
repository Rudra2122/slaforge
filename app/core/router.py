from app.models.tenant import Tenant, SLATier
from app.core.rate_limiter import rate_limiter, redis_client
import time

# SLA latency budgets per tier (p95 targets in ms)
SLA_BUDGETS = {
    SLATier.REALTIME: 200,
    SLATier.STANDARD: 1000,
    SLATier.BATCH: 999999,
}

# Model latency estimates (updated dynamically from recent p95)
MODEL_LATENCY_ESTIMATE = {
    "small": 100.0,   # ms, updated at runtime
    "large": 500.0,
}

async def get_recent_p95(model: str) -> float:
    """
    Reads last 100 latency samples from Redis for p95 estimate.
    Updated by the inference endpoint after every request.
    """
    key = f"latency_samples:{model}"
    samples = await redis_client.lrange(key, -100, -1)
    if not samples:
        return MODEL_LATENCY_ESTIMATE[model]
    sorted_samples = sorted(float(s) for s in samples)
    idx = int(len(sorted_samples) * 0.95)
    return sorted_samples[min(idx, len(sorted_samples) - 1)]

async def record_latency(model: str, latency_ms: float):
    """Push latency sample to Redis ring buffer."""
    key = f"latency_samples:{model}"
    pipe = redis_client.pipeline()
    pipe.rpush(key, latency_ms)
    pipe.ltrim(key, -200, -1)   # keep last 200 samples
    await pipe.execute()

async def get_queue_depth() -> dict:
    """Returns current queue depth per model from Redis."""
    small_q = await redis_client.llen("queue:small")
    large_q = await redis_client.llen("queue:large")
    return {"small": small_q, "large": large_q}

class AdaptiveRouter:
    """
    Routing decision logic:

    REALTIME tier  → always try large model first (best quality),
                     fall back to small if large queue is backed up
    STANDARD tier  → route to small unless:
                       a) small p95 is approaching SLA budget, OR
                       b) prompt is long (>200 tokens) suggesting complexity
    BATCH tier     → always small model, no exceptions
    """

    async def route(self, tenant: Tenant, prompt: str) -> tuple[str, str]:
        """
        Returns: (model_choice: "small"|"large", reason: str)
        """
        tier = tenant.sla_tier
        sla_budget = SLA_BUDGETS[tier]
        prompt_token_count = len(prompt.split())

        small_p95 = await get_recent_p95("small")
        large_p95 = await get_recent_p95("large")
        queues = await get_queue_depth()

        # BATCH: always small
        if tier == SLATier.BATCH:
            return "small", "batch_tier_always_small"

        # REALTIME: try large unless it's backed up
        if tier == SLATier.REALTIME:
            if queues["large"] < 5 and large_p95 < sla_budget:
                return "large", "realtime_tier_large_model"
            elif small_p95 < sla_budget:
                return "small", "realtime_tier_large_backed_up_fallback_small"
            else:
                return "large", "realtime_tier_forced_large_no_good_option"

        # STANDARD: intelligent routing
        # If small model p95 is within 80% of SLA budget, escalate to large
        if small_p95 > sla_budget * 0.8:
            return "large", f"standard_small_p95_{small_p95:.0f}ms_near_sla_{sla_budget}ms"

        # Long prompts → large model for quality
        if prompt_token_count > 200:
            return "large", f"standard_long_prompt_{prompt_token_count}_tokens"

        # Large model queue is free and small is borderline → upgrade
        if queues["large"] == 0 and small_p95 > sla_budget * 0.5:
            return "large", "standard_opportunistic_upgrade_large_queue_free"

        # Default: small model for standard tier
        return "small", f"standard_small_p95_{small_p95:.0f}ms_within_budget"

router = AdaptiveRouter()