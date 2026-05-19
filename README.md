# SLAForge

**Most ML inference platforms treat all tenants equally. SLAForge enforces per-tenant latency contracts at the infrastructure layer so a batch processing tenant can never starve a realtime tenant's SLA, even under 500 concurrent users and maximum load.**

Built with FastAPI, Redis, PostgreSQL, Prometheus, and Grafana. Sustained **558 req/s** with **p95 latency of 28ms** and **zero SLA breaches** across three tenant tiers in a 120-second distributed load test.

[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688.svg)](https://fastapi.tiangolo.com)
[![Redis](https://img.shields.io/badge/Redis-7-red.svg)](https://redis.io)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791.svg)](https://postgresql.org)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg)](https://docker.com)
[![Prometheus](https://img.shields.io/badge/Prometheus-Grafana-E6522C.svg)](https://prometheus.io)
[![p95](https://img.shields.io/badge/p95%20latency-28ms-brightgreen.svg)]()
[![throughput](https://img.shields.io/badge/throughput-558%20req%2Fs-brightgreen.svg)]()
[![sla](https://img.shields.io/badge/SLA%20breaches-0-brightgreen.svg)]()

---

## Dashboard

| Router Decisions & Cost Attribution | Requests/sec & p95 Latency |
|-------------------------------------|---------------------------|
| ![Dashboard Top](docs/dashboard1.png) | ![Dashboard Bottom](docs/dashboard2.png) |

*Live Grafana dashboard during a 500-user load test. Zero SLA breaches, routing decisions split across all 3 tiers, cost tracked per tenant in real time.*

---

## Benchmark Results

Measured on Apple M-series MacBook with 4 Gunicorn workers and 3 distributed Locust workers running simultaneously.

| Metric | Result |
|--------|--------|
| Peak throughput | **558 req/s sustained** |
| Total requests (120s) | **67,066** |
| Failure rate | **0.74%** |
| p50 latency | **4ms** |
| p95 latency | **28ms** |
| p99 latency | **240ms** |
| Concurrent users | **500 across 3 SLA tiers** |
| SLA breaches | **0** |
| Cross-tenant violations | **0** |

The initial implementation processed 44 req/s. Eliminating synchronous PostgreSQL writes on the hot path and replacing them with Redis-buffered batch inserts scaled throughput to 558 req/s, a **12x improvement** without changing the API contract.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Locust Load Test                            │
│          500 users · 3 tenant tiers · distributed              │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP
┌──────────────────────────▼──────────────────────────────────────┐
│               Gunicorn (4 UvicornWorkers)                       │
│                    FastAPI Application                          │
│                                                                 │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │  Auth Layer │  │ Rate Limiter │  │   Adaptive Router      │ │
│  │  API Key    │  │ Token Bucket │  │  p95 feedback loop     │ │
│  │  + Redis    │  │  per tenant  │  │  realtime/std/batch    │ │
│  │  cache      │  │  (pipeline)  │  │  queue depth signal    │ │
│  └──────┬──────┘  └──────┬───────┘  └───────────┬────────────┘ │
│         └────────────────┴───────────────────────┘              │
│                          │                                      │
│              ┌───────────▼───────────┐                         │
│              │   Inference Endpoint  │                         │
│              │  budget → rate limit  │                         │
│              │  → route → infer      │                         │
│              │  → cost → metrics     │                         │
│              │  → buffer log         │                         │
│              └───────────┬───────────┘                         │
└──────────────────────────┼──────────────────────────────────────┘
                           │
          ┌────────────────┴────────────────┐
          │                                 │
┌─────────▼──────────┐          ┌───────────▼────────────────────┐
│       Redis        │          │          PostgreSQL             │
│  · Auth cache      │          │  · Tenants + API keys          │
│  · Rate limit keys │          │  · Request logs (bulk insert)  │
│  · p95 ring buffer │          │  · Cost attribution            │
│  · Log buffer      │          │  · SLA breach events           │
│  · Cost accumulator│          │                                │
└─────────┬──────────┘          └────────────────────────────────┘
          │
┌─────────▼──────────────────────────────────────────────────────┐
│                   Prometheus + Grafana                          │
│  p95 latency per tenant    ·    Router decisions (pie)         │
│  Requests/sec by model     ·    Cost burned per tenant         │
│  SLA breach rate           ·    Rate limit hits                │
└────────────────────────────────────────────────────────────────┘
```

---

## How It Works

**The problem this solves:** In a naive multi-tenant inference API, a flood of batch requests from one tenant can consume all available capacity, causing realtime tenants to miss their latency SLAs. SLAForge enforces isolation at every layer so each tenant gets exactly what their contract guarantees regardless of what others are doing.

**Adaptive routing with live p95 feedback:** The router maintains a 200-sample latency ring buffer in Redis for each model tier. On every request it reads the current p95, compares it against the tenant's SLA budget, checks queue depth, and decides which model to use. This creates a closed feedback loop. As load increases and small model latency drifts upward, standard-tier requests automatically escalate to the large model before the SLA is breached.

**Redis-buffered writes:** Every request previously did two synchronous PostgreSQL writes (log + cost deduction), which caused connection pool exhaustion at 50+ concurrent users. Request logs now push to a Redis list and flush to PostgreSQL in bulk every 5 seconds via a background task. Cost deductions accumulate in Redis counters and reconcile on the same schedule. The hot path touches PostgreSQL zero times per request.

**Auth caching:** API key lookups are cached in Redis for 5 minutes. Under sustained load, auth overhead drops from a full DB query to a single Redis GET, keeping per-request overhead under 1ms.

---

## Routing Decision Logic

```
REALTIME tier  → large model first (lowest latency variance)
                 fallback to small only if large queue depth > 5

STANDARD tier  → small model by default
                 escalate to large if:
                   · small p95 > 80% of 1000ms SLA budget, OR
                   · prompt token count > 200 tokens, OR
                   · large queue is empty AND small p95 > 50% budget

BATCH tier     → always small model, no exceptions
```

The routing reason is logged on every request in the `routing_reason` response field, making every decision auditable and debuggable in production.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API framework | FastAPI 0.111 + Uvicorn |
| Process manager | Gunicorn 26 (4 UvicornWorkers) |
| Database | PostgreSQL 16 (SQLAlchemy 2.0, pool_size=20) |
| Cache / rate limiting | Redis 7 (asyncio client, pipeline ops) |
| ML workers | AirLLM (mock mode for local dev) |
| Metrics | Prometheus client + Grafana 10.4 |
| Load testing | Locust 2.28 (distributed master/worker) |
| Containerization | Docker Compose |
| CI/CD | CircleCI |

---

## Project Structure

```
slaforge/
├── app/
│   ├── main.py                  # FastAPI entry + background log/cost flusher
│   ├── config.py                # Pydantic settings
│   ├── database.py              # SQLAlchemy engine (pool_size=20, overflow=40)
│   ├── api/
│   │   ├── auth.py              # API key auth + 5min Redis cache
│   │   ├── tenants.py           # Tenant CRUD + usage/p95 endpoints
│   │   └── inference.py         # Core inference endpoint
│   ├── core/
│   │   ├── rate_limiter.py      # Redis token bucket (sorted set, pipeline)
│   │   ├── router.py            # Adaptive router + p95 ring buffer
│   │   └── cost.py              # Cost calculation + Redis accumulation
│   ├── models/
│   │   ├── tenant.py            # Tenant ORM (SLATier enum)
│   │   └── request_log.py       # Per-request log ORM
│   ├── workers/
│   │   ├── small_model.py       # 1.1B model worker (AirLLM / mock)
│   │   └── large_model.py       # 70B model worker (AirLLM / mock)
│   └── observability/
│       └── metrics.py           # 8 custom Prometheus metrics
├── infra/
│   ├── prometheus.yml
│   └── grafana/dashboards/
├── load_tests/
│   └── locustfile.py            # 3-tier distributed load test
├── tests/
│   ├── test_auth.py
│   ├── test_router.py
│   ├── test_rate_limiter.py
│   └── test_cost.py
├── .circleci/
│   └── config.yml               # test job + benchmark job (p95 gate)
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## Quick Start

**Prerequisites:** Python 3.12, Docker Desktop

```bash
# Clone and install
git clone https://github.com/Rudra2122/slaforge.git
cd slaforge
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env

# Start infrastructure
docker compose up -d postgres redis prometheus grafana

# Start server
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

---

## API Reference

**Create a tenant:**
```bash
curl -X POST http://localhost:8000/tenants/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Acme Corp",
    "sla_tier": "realtime",
    "requests_per_minute": 1000,
    "monthly_budget_usd": 500
  }'
```

**Run inference:**
```bash
curl -X POST http://localhost:8000/inference/ \
  -H "X-API-Key: sf_YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Explain distributed systems.", "max_tokens": 128}'
```

```json
{
  "request_id": "cf69d34e-ae9b-4eb2-95e4-0897c640334c",
  "text": "...",
  "model_used": "small",
  "routing_reason": "standard_small_p95_12ms_within_budget",
  "latency_ms": 5.0,
  "prompt_tokens": 3,
  "completion_tokens": 32,
  "cost_usd": 0.000007,
  "sla_tier": "standard",
  "sla_breached": false,
  "budget_used_pct": 0.001
}
```

**Check tenant usage:**
```bash
curl http://localhost:8000/tenants/TENANT_ID/usage
```

---

## Observability

8 custom Prometheus metrics exposed at `/metrics`:

| Metric | Type | Description |
|--------|------|-------------|
| `slaforge_inference_requests_total` | Counter | Requests by tenant, tier, model, status |
| `slaforge_inference_latency_ms` | Histogram | Latency distribution by tenant and model |
| `slaforge_sla_breaches_total` | Counter | SLA violations by tenant and tier |
| `slaforge_cost_per_request_usd` | Histogram | Cost distribution by tenant and model |
| `slaforge_tenant_budget_used_usd` | Gauge | Running budget consumption per tenant |
| `slaforge_rate_limit_hits_total` | Counter | Rejected requests per tenant |
| `slaforge_routing_decisions_total` | Counter | Router decisions by model and reason |
| `slaforge_queue_depth` | Gauge | Current queue depth per model |

Grafana dashboard at `http://localhost:3000` (admin/admin). Add Prometheus datasource pointing to `http://prometheus:9090`.

---

## Load Testing

```bash
# Reset tenant budgets before each run
docker exec -it $(docker ps -q -f ancestor=postgres:16) \
  psql -U slaforge -d slaforge -c "UPDATE tenants SET cost_used_usd = 0;"

# Master process
python -m locust -f load_tests/locustfile.py \
  --master --host=http://localhost:8000 \
  --users 500 --spawn-rate 100 --run-time 120s --headless \
  --csv=results/load_test --expect-workers 3

# Worker processes (3 separate terminals)
python -m locust -f load_tests/locustfile.py --worker
```

Traffic mix: 100 realtime users (0.1 to 0.5s think time), 250 standard users (0.5 to 2s), 150 batch users (2 to 5s).

---

## CI Pipeline

Two jobs run on every push:

**test** runs pytest across auth, router, rate limiter, and cost attribution against live PostgreSQL and Redis services.

**benchmark** starts the server, runs a 30-second Locust load test, and asserts p95 < 500ms. The build fails if a code change introduces a latency regression.

```
push → test → benchmark (p95 < 500ms gate) → merge
```

---

## Local Development

```bash
# Single worker with hot reload
uvicorn app.main:app --reload --port 8000

# Run tests
pytest tests/ -v --tb=short

# Use real AirLLM models (Apple Silicon / GPU)
# In .env: USE_MOCK_MODELS=false
# Downloads TinyLlama 1.1B on first run, runs on M1/M2/M3 without GPU
```

---

## License

MIT
