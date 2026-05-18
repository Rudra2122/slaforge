from app.config import settings
from app.models.tenant import Tenant
from app.models.tenant import Tenant as TenantModel
from sqlalchemy.orm import Session

def calculate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    total_tokens = prompt_tokens + completion_tokens
    rate = (
        settings.small_model_cost_per_1k
        if model == "small"
        else settings.large_model_cost_per_1k
    )
    return (total_tokens / 1000) * rate

def check_budget(tenant: Tenant) -> bool:
    return tenant.cost_used_usd < tenant.monthly_budget_usd

def deduct_cost(db: Session, tenant: Tenant, cost: float):
    """Deduct cost using the already-open request session — no new connection needed."""
    tenant.cost_used_usd += cost
    db.add(tenant)
    # don't commit here — let the log write commit everything together

def budget_utilization_pct(tenant: Tenant) -> float:
    if tenant.monthly_budget_usd == 0:
        return 100.0
    return (tenant.cost_used_usd / tenant.monthly_budget_usd) * 100