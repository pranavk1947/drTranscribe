# drTranscribe Backend — Production Architecture on GCP Cloud Run

## Context

The current backend is a well-structured FastAPI app with clean provider abstractions, but it's MVP-grade: in-memory sessions, local filesystem audio, no resilience patterns, no auth, no monitoring. It needs to be production-ready on GCP Cloud Run within 15 days.

---

## Do You Need Temporal / LangChain / LangSmith?

### Temporal — NO

Temporal is for long-running, multi-step distributed workflows (order processing, multi-day sagas, human-in-the-loop approvals). Your pipeline is:

```
audio_chunk → STT (1-3s) → LLM extraction (2-5s) → WebSocket response
```

This is a **short, synchronous pipeline within a single WebSocket connection**. It completes in seconds, not hours. Temporal would add:
- A Temporal server cluster to operate (or Temporal Cloud at ~$200/mo+)
- Worker processes, task queues, activity definitions
- Significant boilerplate for a simple pipeline

**What to use instead:** `tenacity` (retry with backoff) + `pybreaker` (circuit breaker). Two pip packages, zero infrastructure.

The one scenario where Temporal *would* help: if you later need offline batch reprocessing of failed consultations. But a simple Redis-backed DLQ handles that fine for now.

### LangChain — NO

Your extraction is a single LLM call:
```python
response = client.chat.completions.create(
    model="gpt-4.1-mini",
    messages=[system_prompt, user_transcript],
    response_format={"type": "json_object"}
)
```

LangChain would wrap this in `ChatOpenAI | JsonOutputParser | RunnableSequence` — adding 3 layers of abstraction over a 5-line API call. Your existing provider pattern (`base.py` → `azure_gpt.py`, `openai_gpt.py`, etc.) is already cleaner and more debuggable than LangChain's abstractions.

LangChain is valuable when you need RAG pipelines, agent loops, tool calling chains, or complex prompt composition. You have none of those — you have a fixed system prompt + transcript → JSON extraction.

### LangSmith — OPTIONAL (add later if needed)

LangSmith provides LLM observability: prompt/completion tracing, latency tracking, cost monitoring, eval datasets. It IS useful for production LLM apps, but for your scale:

- **GCP Cloud Logging with structured JSON** gives you 80% of the value at zero extra cost
- Log the prompt, response, latency, token count, provider, and session_id as structured fields
- Build Cloud Monitoring dashboards on these logs

If you later want dedicated LLM analytics (prompt versioning, A/B testing prompts, regression detection), add LangSmith or Langfuse incrementally. Don't start with it.

---

## Recommended Production Stack

| Component | Tool | Why |
|-----------|------|-----|
| **Framework** | FastAPI (keep as-is) | Already using, excellent async WebSocket support |
| **Runtime** | Cloud Run (gen2) | Native WebSocket support, scales to zero, up to 60min timeout |
| **Session State** | **Redis via Memorystore** | Sub-ms latency, TTL auto-cleanup, survives instance restarts |
| **Audio Storage** | **Google Cloud Storage (GCS)** | Replaces local filesystem (Cloud Run is ephemeral), cheap, durable |
| **Secrets** | **GCP Secret Manager** | Replaces .env file, auto-rotation, IAM-controlled access |
| **Resilience** | **tenacity + pybreaker** | Retry with exponential backoff + circuit breaker. Two small libraries, zero infra |
| **Monitoring** | **Cloud Logging + Cloud Monitoring** | Native, free tier generous, structured JSON logging |
| **Container** | **Docker + Artifact Registry** | Standard Cloud Run deployment path |
| **CI/CD** | **Cloud Build** or **GitHub Actions** | Automated build → push → deploy |
| **Auth** | **API key validation** (phase 1) | Simple, sufficient for internal/partner use |

### What you DON'T need
- **Kubernetes** — Cloud Run handles scaling, no cluster management
- **Celery/RabbitMQ** — Pipeline is synchronous within WebSocket, no background job queue needed
- **PostgreSQL** — No relational data; Redis for sessions + GCS for audio is sufficient
- **Terraform** (day 1) — `gcloud` CLI for initial setup, add IaC later if team grows

---

## 15-Day Development Plan

### Phase 1: Infrastructure Foundation (Days 1-4)

#### Day 1-2: Dockerize + Cloud Run Baseline
- Write `Dockerfile` (Python 3.11-slim, install deps, copy src)
- Create `cloudbuild.yaml` for Artifact Registry push
- Deploy basic FastAPI to Cloud Run, verify `/health` works
- Configure Cloud Run: min 0 / max 5 instances, 1GB RAM, 1 vCPU, 300s request timeout
- **Files:** New `Dockerfile`, `cloudbuild.yaml`, `.dockerignore`

#### Day 3: GCS Audio Storage
- Replace `audio_storage.py` local filesystem → GCS client
- Upload chunks to `gs://drtranscribe-audio/{session_id}/chunk_NNNN.wav`
- Combined final audio to `gs://drtranscribe-audio/{date}/{session_id}_final.wav`
- Set lifecycle policy: auto-delete temp chunks after 24h
- **Files:** Modify `src/services/audio_storage.py`, add `google-cloud-storage` to requirements

#### Day 4: Redis Session State + Secret Manager
- Provision Memorystore for Redis (Basic tier, 1GB, same region as Cloud Run)
- Replace `SessionManager` in-memory dict → Redis (JSON serialization with TTL)
- Move all API keys from `.env` → Secret Manager
- Load secrets at startup via `google-cloud-secret-manager` SDK
- **Files:** Modify `src/services/session_manager.py`, `src/config/settings.py`

### Phase 2: Resilience Layer (Days 5-8)

#### Day 5-6: Circuit Breaker + Retry for Providers
- Add `tenacity` retry decorator to all provider `transcribe()` and `extract()` methods
  - 3 retries, exponential backoff (1s, 2s, 4s), retry on transient errors only
- Add `pybreaker` circuit breaker per provider
  - Open after 3 consecutive failures, 30s cooldown, half-open probe
- **Files:** Modify all files in `src/providers/transcription/` and `src/providers/extraction/`

#### Day 7: Provider Fallback Chain
- Modify `TranscriptionService` and `ExtractionService` to accept ordered provider list
- On circuit open → automatically try next provider in chain
- STT chain: `groq → gemini → openai`
- LLM chain: `gemini → azure_gpt → openai`
- Config-driven: `settings.yaml` defines priority order
- **Files:** Modify `src/services/transcription_service.py`, `src/services/extraction_service.py`

#### Day 8: WebSocket Hardening
- Add connection timeout (max session duration: 60min)
- Heartbeat/ping-pong every 30s to detect stale connections
- Graceful session cleanup on abnormal disconnect
- Rate limit: max 1 audio chunk per second per connection
- **Files:** Modify `src/websocket_handler.py`

### Phase 3: Observability + Security (Days 9-11)

#### Day 9: Structured Logging
- Replace print/basic logging → `structlog` with JSON output
- Every log line includes: `session_id`, `provider`, `latency_ms`, `event_type`
- Log extraction results: field diffs, token counts, provider used
- Cloud Logging auto-ingests JSON → queryable fields
- **Files:** New `src/utils/logging.py`, modify all service files

#### Day 10: Health Checks + Monitoring
- `/health` — liveness (am I running?)
- `/readiness` — can I serve? (Redis connected, at least 1 STT + 1 LLM provider healthy)
- Provider health: periodic ping to each provider API (background task)
- Cloud Monitoring alerts: error rate > 5%, p95 latency > 10s, circuit breaker open
- **Files:** Modify `src/main.py`, new `src/services/health_monitor.py`

#### Day 11: Authentication
- API key auth for WebSocket (passed as query param or first message)
- Keys stored in Secret Manager, validated on connection
- CORS restricted to known origins (Chrome extension ID, EMR domain)
- **Files:** Modify `src/main.py`, `src/websocket_handler.py`

### Phase 4: Testing + Deployment (Days 12-15)

#### Day 12: Integration Tests
- Test each provider with real API calls (small audio sample)
- Test circuit breaker: mock provider failure → verify fallback
- Test Redis session lifecycle: create → update → expire
- Test GCS audio upload + cleanup
- **Files:** New `tests/` directory

#### Day 13: Load Testing
- Use `locust` or `websocket-bench` to simulate 10-20 concurrent sessions
- Identify bottlenecks: Cloud Run instance count, Redis connections, provider rate limits
- Tune: instance scaling, connection pooling, chunk processing concurrency

#### Day 14: CI/CD Pipeline
- Cloud Build trigger on push to `main`
- Build → test → push to Artifact Registry → deploy to Cloud Run (staging)
- Manual promotion: staging → production
- **Files:** Finalize `cloudbuild.yaml`

#### Day 15: Staging Deployment + E2E Testing
- Full end-to-end: Chrome Extension → Cloud Run → STT → LLM → WebSocket response
- Test provider failover scenario (disable primary, verify fallback)
- Test session persistence (restart Cloud Run instance, verify session survives in Redis)
- Document runbook: deployment, rollback, monitoring dashboards

---

## Cost Estimate (Monthly, Low Traffic)

| Service | Spec | Est. Cost |
|---------|------|-----------|
| Cloud Run | 1 vCPU, 1GB, min 0 instances | ~$5-15 (pay per request) |
| Memorystore Redis | Basic 1GB | ~$35 |
| Cloud Storage | <10GB audio | ~$1 |
| Secret Manager | <10 secrets | ~$0 (free tier) |
| Cloud Build | <120 min/day | ~$0 (free tier) |
| **Total infra** | | **~$40-50/mo** |
| STT API costs | Groq (free) / Gemini ($0.006/min) | Variable |
| LLM API costs | Gemini Flash (~$0.01/1K tokens) | Variable |

---

## Frontend vs Backend Task Split

### Frontend Team (Chrome Extension + EMR)
- Broadcast Channel integration (extension ↔ EMR page)
- Overlay panel UI (already done)
- Audio capture (AudioWorklet + WAV encoder — already done)
- Export module (PDF, email, clipboard — already done)
- WebSocket reconnection logic on the client side
- EMR demo page

### Backend Team (Cloud Run Service)
- Everything in this plan: Dockerize, GCS, Redis, circuit breakers, fallback chains, auth, monitoring, CI/CD
- WebSocket handler hardening
- Provider resilience layer
- Structured logging + health monitoring
- Load testing + performance tuning

---

## Key Dependencies to Add

```
# requirements.txt additions
tenacity>=8.2.0          # Retry with backoff
pybreaker>=1.0.0         # Circuit breaker
structlog>=23.0.0        # Structured logging
google-cloud-storage>=2.0.0
google-cloud-secret-manager>=2.0.0
redis>=5.0.0             # Redis client
locust>=2.0.0            # Load testing (dev only)
```

---

## Verification

1. `docker build` + `docker run` locally, hit `/health`
2. Deploy to Cloud Run staging, verify WebSocket connects from extension
3. Run a full consultation: start → audio chunks → extraction updates → stop
4. Kill Cloud Run instance mid-session → verify session recovers from Redis
5. Disable primary STT provider → verify fallback kicks in within 500ms
6. Check Cloud Logging for structured JSON logs with session_id correlation


===
Have You explored other wasy to get transcripts,before building of your own?
                                                                                                
there are 3 ways to get live transcripts from a Google Meet call — none are clean APIs:

  1. DOM Scraping of Live Captions (most common)

  - Extensions like Tactiq and Fireflies use MutationObserver to watch Meet's caption DOM elements in real-time
  - Works on all plans (live captions are free)
  - Catch: User must manually enable captions each call, and Google regularly breaks selectors with UI updates

  2. Google Meet Media API (official, but gated)

  - Provides real-time audio/video streams from a meeting
  - Still in Developer Preview — you must apply and get approved
  - Catch: ALL participants must be enrolled in the program, and it gives you raw audio, not transcripts — you'd still need your own STT

  3. Meeting Bot (e.g., Recall.ai, Fireflies bot)

  - A bot joins the call as a participant and captures audio/captions
  - Catch: Requires a visible bot participant in the call, which is intrusive for medical consultations

  ---
  Bottom line: There is no Google API that gives you real-time transcript text from a live Meet call. The closest thing is scraping
  captions from the DOM, which is what popular extensions do — but it's fragile and you still need your own STT for reliability.
