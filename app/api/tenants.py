from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.tenant import Tenant, SLATier
from app.schemas.tenant import TenantCreate, TenantResponse
import uuid, secrets

router = APIRouter(prefix="/tenants", tags=["tenants"])

@router.post("/", response_model=TenantResponse)
def create_tenant(payload: TenantCreate, db: Session = Depends(get_db)):
    api_key = f"sf_{secrets.token_urlsafe(32)}"
    tenant = Tenant(
        id=str(uuid.uuid4()),
        name=payload.name,
        api_key=api_key,
        sla_tier=payload.sla_tier,
        requests_per_minute=payload.requests_per_minute,
        monthly_budget_usd=payload.monthly_budget_usd,
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant

@router.get("/{tenant_id}", response_model=TenantResponse)
def get_tenant(tenant_id: str, db: Session = Depends(get_db)):
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant

@router.get("/{tenant_id}/usage")
def get_tenant_usage(tenant_id: str, db: Session = Depends(get_db)):
    from app.models.request_log import RequestLog
    from sqlalchemy import func
    
    stats = db.query(
        func.count(RequestLog.id).label("total_requests"),
        func.sum(RequestLog.cost_usd).label("total_cost"),
        func.avg(RequestLog.latency_ms).label("avg_latency"),
        func.percentile_cont(0.95).within_group(
            RequestLog.latency_ms.asc()
        ).label("p95_latency"),
        func.sum(RequestLog.sla_breached).label("sla_breaches"),
    ).filter(RequestLog.tenant_id == tenant_id).first()
    
    return {
        "tenant_id": tenant_id,
        "total_requests": stats.total_requests or 0,
        "total_cost_usd": round(stats.total_cost or 0, 6),
        "avg_latency_ms": round(stats.avg_latency or 0, 2),
        "p95_latency_ms": round(stats.p95_latency or 0, 2),
        "sla_breaches": stats.sla_breaches or 0,
    }