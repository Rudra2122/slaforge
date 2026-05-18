from prometheus_client import Counter, Histogram, Gauge, Summary

# ── Inference metrics ─────────────────────────────────────────────────────────
INFERENCE_REQUESTS = Counter(
    "slaforge_inference_requests_total",
    "Total inference requests",
    ["tenant_id", "sla_tier", "model_used", "status"]
)

INFERENCE_LATENCY = Histogram(
    "slaforge_inference_latency_ms",
    "Inference latency in ms",
    ["tenant_id", "model_used"],
    buckets=[50, 100, 200, 300, 500, 750, 1000, 2000, 5000]
)

SLA_BREACHES = Counter(
    "slaforge_sla_breaches_total",
    "Total SLA breaches",
    ["tenant_id", "sla_tier"]
)

# ── Cost metrics ──────────────────────────────────────────────────────────────
COST_PER_REQUEST = Histogram(
    "slaforge_cost_per_request_usd",
    "Cost per request in USD",
    ["tenant_id", "model_used"],
    buckets=[0.0001, 0.0005, 0.001, 0.005, 0.01, 0.05]
)

TENANT_BUDGET_USED = Gauge(
    "slaforge_tenant_budget_used_usd",
    "Budget used this month per tenant",
    ["tenant_id"]
)

# ── Rate limiting metrics ─────────────────────────────────────────────────────
RATE_LIMIT_HITS = Counter(
    "slaforge_rate_limit_hits_total",
    "Requests rejected by rate limiter",
    ["tenant_id"]
)

# ── Routing metrics ───────────────────────────────────────────────────────────
ROUTING_DECISIONS = Counter(
    "slaforge_routing_decisions_total",
    "Router model selection decisions",
    ["model_chosen", "reason"]
)

QUEUE_DEPTH = Gauge(
    "slaforge_queue_depth",
    "Current queue depth per model",
    ["model"]
)