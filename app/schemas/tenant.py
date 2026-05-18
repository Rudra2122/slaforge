from pydantic import BaseModel
from app.models.tenant import SLATier

class TenantCreate(BaseModel):
    name: str
    sla_tier: SLATier = SLATier.STANDARD
    requests_per_minute: int = 60
    monthly_budget_usd: float = 10.0

class TenantResponse(BaseModel):
    id: str
    name: str
    api_key: str
    sla_tier: SLATier
    requests_per_minute: int
    monthly_budget_usd: float
    cost_used_usd: float
    is_active: bool

    class Config:
        from_attributes = True