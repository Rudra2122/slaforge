from pydantic import BaseModel

class InferenceRequest(BaseModel):
    prompt: str
    max_tokens: int = 128

class InferenceResponse(BaseModel):
    request_id: str
    text: str
    model_used: str
    routing_reason: str
    latency_ms: float
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    sla_tier: str
    sla_breached: bool
    budget_used_pct: float