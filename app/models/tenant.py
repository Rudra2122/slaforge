from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, Enum
from sqlalchemy.sql import func
import enum
from app.database import Base

class SLATier(str, enum.Enum):
    REALTIME = "realtime"    # p95 < 200ms, always large model if needed
    STANDARD = "standard"    # p95 < 1000ms, router decides
    BATCH = "batch"          # no latency SLA, always small model

class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(String, primary_key=True)           # UUID
    name = Column(String, nullable=False)
    api_key = Column(String, unique=True, nullable=False)
    sla_tier = Column(Enum(SLATier), default=SLATier.STANDARD)
    
    # Rate limits
    requests_per_minute = Column(Integer, default=60)
    max_tokens_per_request = Column(Integer, default=512)
    
    # Budget
    monthly_budget_usd = Column(Float, default=10.0)
    cost_used_usd = Column(Float, default=0.0)
    
    # Status
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())