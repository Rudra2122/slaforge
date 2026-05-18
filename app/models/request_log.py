from sqlalchemy import Column, String, Float, Integer, DateTime, Enum
from sqlalchemy.sql import func
from app.database import Base

class RequestLog(Base):
    __tablename__ = "request_logs"

    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False)
    
    # Routing decision
    model_used = Column(String)          # "small" or "large"
    routing_reason = Column(String)      # why router chose this model
    
    # Performance
    latency_ms = Column(Float)
    prompt_tokens = Column(Integer)
    completion_tokens = Column(Integer)
    
    # Cost
    cost_usd = Column(Float)
    
    # SLA
    sla_tier = Column(String)
    sla_breached = Column(Integer, default=0)   # 0 or 1
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())