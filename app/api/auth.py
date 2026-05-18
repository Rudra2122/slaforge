from fastapi import HTTPException, Security, Depends
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.tenant import Tenant
from app.core.rate_limiter import redis_client
import json

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

async def get_current_tenant(
    api_key: str = Security(api_key_header),
    db: Session = Depends(get_db)
) -> Tenant:
    cache_key = f"tenant_auth:{api_key}"
    cached = await redis_client.get(cache_key)
    if cached:
        tenant_id = json.loads(cached)["id"]
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if tenant:
            return tenant

    tenant = db.query(Tenant).filter(
        Tenant.api_key == api_key,
        Tenant.is_active == True
    ).first()

    if not tenant:
        raise HTTPException(status_code=401, detail="Invalid or inactive API key")

    await redis_client.setex(cache_key, 300, json.dumps({"id": tenant.id}))
    return tenant