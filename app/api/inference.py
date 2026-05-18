from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import uuid, time, json

from app.database import get_db
from app.api.auth import get_current_tenant
from app.models.tenant import Tenant
from app.models.request_log import RequestLog
from app.core.rate_limiter import rate_limiter, redis_client
from app.core.router import router as adaptive_router, record_latency
from app.core.cost import calculate_cost, check_budget, budget_utilization_pct
from app.workers.small_model import small_model
from app.workers.large_model import large_model
from app.observability.metrics import (
    INFERENCE_REQUESTS, INFERENCE_LATENCY, SLA_BREACHES,
    COST_PER_REQUEST, TENANT_BUDGET_USED, RATE_LIMIT_HITS,
    ROUTING_DECISIONS
)
from app.schemas.inference import InferenceRequest, InferenceResponse

SLA_BUDGETS = {"realtime": 200, "standard": 1000, "batch": 999999}

router = APIRouter(prefix="/inference", tags=["inference"])

@router.post("/", response_model=InferenceResponse)
async def run_inference(
    payload: InferenceRequest,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    # 1. Budget check
    if not check_budget(tenant):
        raise HTTPException(
            status_code=429,
            detail=f"Monthly budget exhausted. Used: ${tenant.cost_used_usd:.4f} / ${tenant.monthly_budget_usd:.2f}"
        )

    # # 2. Rate limit check
    # allowed, rate_info = await rate_limiter.is_allowed(tenant)
    # if not allowed:
    #     RATE_LIMIT_HITS.labels(tenant_id=tenant.id).inc()
    #     raise HTTPException(
    #         status_code=429,
    #         detail=f"Rate limit exceeded. {rate_info['retry_after_seconds']}s until reset.",
    #         headers={"Retry-After": str(rate_info["retry_after_seconds"])},
    #     )

    # 3. Routing decision
    model_choice, routing_reason = await adaptive_router.route(tenant, payload.prompt)
    ROUTING_DECISIONS.labels(model_chosen=model_choice, reason=routing_reason).inc()

    # 4. Inference
    try:
        if model_choice == "small":
            result = await small_model.generate(payload.prompt, payload.max_tokens)
        else:
            result = await large_model.generate(payload.prompt, payload.max_tokens)
    except Exception as e:
        INFERENCE_REQUESTS.labels(
            tenant_id=tenant.id, sla_tier=tenant.sla_tier,
            model_used=model_choice, status="error"
        ).inc()
        raise HTTPException(status_code=500, detail=f"Model inference failed: {str(e)}")

    latency_ms = result["latency_ms"]

    # 5. Record latency for router feedback loop
    await record_latency(model_choice, latency_ms)

    # 6. SLA breach detection
    sla_budget = SLA_BUDGETS.get(tenant.sla_tier.value, 1000)
    sla_breached = 1 if latency_ms > sla_budget else 0
    if sla_breached:
        SLA_BREACHES.labels(tenant_id=tenant.id, sla_tier=tenant.sla_tier).inc()

    # 7. Cost calculation — accumulate in Redis, flushed to DB by background task
    cost = calculate_cost(model_choice, result["prompt_tokens"], result["completion_tokens"])
    try:
        await redis_client.incrbyfloat(f"cost_accum:{tenant.id}", cost)
    except Exception:
        pass 
    
    # 8. Prometheus metrics
    INFERENCE_REQUESTS.labels(
        tenant_id=tenant.id, sla_tier=tenant.sla_tier,
        model_used=model_choice, status="success"
    ).inc()
    INFERENCE_LATENCY.labels(tenant_id=tenant.id, model_used=model_choice).observe(latency_ms)
    COST_PER_REQUEST.labels(tenant_id=tenant.id, model_used=model_choice).observe(cost)
    TENANT_BUDGET_USED.labels(tenant_id=tenant.id).set(tenant.cost_used_usd)

    # 9. Buffer log to Redis — background task flushes to DB every 5s
    log_id = str(uuid.uuid4())
    log_data = {
        "id": log_id,
        "tenant_id": tenant.id,
        "model_used": model_choice,
        "routing_reason": routing_reason,
        "latency_ms": latency_ms,
        "prompt_tokens": result["prompt_tokens"],
        "completion_tokens": result["completion_tokens"],
        "cost_usd": cost,
        "sla_tier": tenant.sla_tier.value,
        "sla_breached": sla_breached,
    }
    await redis_client.lpush("log_buffer", json.dumps(log_data))

    return InferenceResponse(
        request_id=log_id,
        text=result["text"],
        model_used=model_choice,
        routing_reason=routing_reason,
        latency_ms=round(latency_ms, 2),
        prompt_tokens=result["prompt_tokens"],
        completion_tokens=result["completion_tokens"],
        cost_usd=round(cost, 6),
        sla_tier=tenant.sla_tier,
        sla_breached=bool(sla_breached),
        budget_used_pct=round(budget_utilization_pct(tenant), 2),
    )