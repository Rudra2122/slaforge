from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from app.database import engine, SessionLocal
from app.models import tenant as tenant_model, request_log as log_model
from app.models.tenant import Tenant as TenantModel
from app.models.request_log import RequestLog
from app.api import tenants, inference
from app.core.rate_limiter import redis_client
import asyncio, json

tenant_model.Base.metadata.create_all(bind=engine)
log_model.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="SLAForge",
    description="Multi-tenant ML Inference Platform with SLA Enforcement",
    version="1.0.0",
)

Instrumentator().instrument(app).expose(app)
app.include_router(tenants.router)
app.include_router(inference.router)

@app.get("/health")
def health():
    return {"status": "ok", "service": "SLAForge"}

async def flush_buffers():
    while True:
        await asyncio.sleep(5)
        db = SessionLocal()
        try:
            # Flush log buffer in bulk
            batch = []
            for _ in range(10000):  # max 10k per flush cycle
                item = await redis_client.rpop("log_buffer")
                if not item:
                    break
                batch.append(json.loads(item))
            if batch:
                db.bulk_insert_mappings(RequestLog, batch)
                db.commit()

            # Flush cost accumulators
            keys = await redis_client.keys("cost_accum:*")
            for key in keys:
                val = await redis_client.getdel(key)
                if val:
                    tenant_id = key.split(":")[1]
                    db.query(TenantModel).filter(
                        TenantModel.id == tenant_id
                    ).update({"cost_used_usd": TenantModel.cost_used_usd + float(val)})
            if keys:
                db.commit()
        except Exception as e:
            print(f"Flush error: {e}")
        finally:
            db.close()

@app.on_event("startup")
async def startup():
    asyncio.create_task(flush_buffers())