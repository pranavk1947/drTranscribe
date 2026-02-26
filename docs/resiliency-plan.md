# Loop-Scribe — Resiliency Architecture Plan

## Context

The audio processing pipeline has **zero resiliency mechanisms** today. Every provider call is single-shot — if it fails, data is lost. Session state is in-memory — if Cloud Run restarts, all active consultations are gone. This document evaluates Temporal, Pub/Sub, and a lightweight in-process approach, and recommends the best fit.

---

## Current Resiliency Gaps

| Stage | What Happens on Failure | Data Lost? | Code Reference |
|-------|------------------------|------------|----------------|
| **STT (Groq)** | Exception logged, chunk dropped. No retry. | Audio transcription lost (bytes still on /tmp) | `websocket_handler.py:364-367` |
| **Extraction (Gemini)** | Background task logs error, session continues with stale data | Latest extraction update missed | `websocket_handler.py:442-448` |
| **Session State** | In-memory dict — all sessions lost on instance restart | All transcripts, extractions, patient data | `session_manager.py:11-12` |
| **Audio Storage** | Async write to /tmp (no fsync). Combined to local disk at session end only | Audio lost if instance dies mid-session | `audio_storage.py:56` |
| **Provider Outage** | Single provider configured — no fallback chain | Entire pipeline halted | `settings.yaml:2,7` |

---

## Option Evaluation

### Option A: Temporal — OVERKILL

| Criterion | Assessment |
|-----------|------------|
| **Implementation** | 8-12 days. Requires Temporal server (Docker + PostgreSQL), worker processes separate from WebSocket server, activity/workflow definitions, signal-based communication. |
| **Latency** | +50-200ms per activity hop (poll-based task dispatch). Pipeline needs sub-5s. |
| **Infra Cost** | Self-hosted: $55-120/mo (GCE + PostgreSQL). Temporal Cloud: $200+/mo. |
| **Operational Overhead** | HIGH. Must monitor/upgrade Temporal server, manage workers. |
| **Cloud Run Fit** | POOR. Workers need long-running poll loops — Cloud Run scales to zero and bills per request. Would need separate GCE/GKE for workers. |
| **Solves All Gaps?** | Yes — durable workflows, built-in retry, state persistence. |

**Verdict:** Temporal is designed for multi-step sagas spanning hours or days. Our pipeline is a single WebSocket connection lasting minutes. Wrong abstraction level.

### Option B: Google Pub/Sub — WRONG TOOL

| Criterion | Assessment |
|-----------|------------|
| **Implementation** | 6-8 days. Topics, push subscriptions, IAM config, message serialization, dead-letter topics, ordering keys, and a separate mechanism to push results back to WebSocket. |
| **Latency** | +40-200ms per pub/sub hop (two hops in pipeline). Cold start risk on push subscribers. |
| **Infra Cost** | ~free at this scale ($40/TB). |
| **Operational Overhead** | LOW-MODERATE. Monitor DLQ backlogs, subscription health. |
| **Cloud Run Fit** | Good for push subscriptions, but breaks the clean synchronous WS→result path. |
| **Solves All Gaps?** | PARTIALLY. Retry: yes. DLQ: yes. Session state: NO (still needs Redis). Circuit breaker: NO. |

**Verdict:** Pub/Sub is a message bus, not a state machine. It adds latency, doesn't solve session persistence, and breaks the direct WebSocket→result path. The WebSocket IS our delivery guarantee — if it dies, the session is over or can be resumed from Redis. No need for a message bus in the hot path.

### Option C: tenacity + pybreaker + Redis — RECOMMENDED

| Criterion | Assessment |
|-----------|------------|
| **Implementation** | 4-5 days. Decorators on existing methods, Redis swap for in-memory dict, GCS upload addition. |
| **Latency** | ~0ms on happy path. Retry adds backoff only on failure. Circuit breaker REDUCES latency on sustained failure (fail-fast). |
| **Infra Cost** | ~$0 incremental (Redis Memorystore already exists). GCS: ~$1/mo for audio. |
| **Operational Overhead** | LOW. Memorystore is managed. tenacity/pybreaker are pure Python. |
| **Cloud Run Fit** | EXCELLENT. All in-process. Redis via VPC connector. No external orchestration. Scales to zero cleanly. |
| **Solves All Gaps?** | YES. See detailed breakdown below. |

---

## Comparison Summary

| | Temporal | Pub/Sub | **tenacity + pybreaker + Redis** |
|---|---|---|---|
| Implementation | 8-12 days | 6-8 days | **4-5 days** |
| Latency overhead | 50-200ms/hop | 40-200ms/hop | **~0ms happy path** |
| Infra cost | $55-200+/mo | ~free | **~$0 (Redis exists)** |
| Cloud Run fit | Poor | OK | **Excellent** |
| Solves all gaps | Yes | Partially | **Yes** |

---

## Recommended Architecture (Option C)

```
Audio Chunk arrives via WebSocket
    │
    ├─ audio_bytes held in local scope (retry source for immediate retries)
    │
    ▼
Save to /tmp + upload to GCS (fire-and-forget, non-blocking)
    │
    ▼
TranscriptionService.transcribe(audio_bytes)
    │  tenacity: 3 retries, exponential backoff 0.5s → 1s → 2s
    │  pybreaker: open after 3 consecutive failures, 30s cooldown
    │  fallback chain: groq → gemini → openai
    │  retry source: same audio_bytes in local scope
    │
    ├─ ALL FAIL? → push to Redis DLQ (with GCS path for later retry)
    │
    ▼
ExtractionService.extract(full_transcript)
    │  tenacity: 2 retries, exponential backoff 1s → 2s
    │  pybreaker: open after 3 consecutive failures, 60s cooldown
    │  fallback chain: gemini → openai → groq
    │
    ▼
Redis: persist session state (transcript chunks + extraction result)
    │
    ▼
WebSocket: send extraction_update to client
```

---

## The Audio Retry Question

**"If STT fails and we retry, where does the audio come from?"**

| Retry Type | When | Audio Source | How |
|---|---|---|---|
| **Immediate** (tenacity) | 0-4 seconds | `audio_bytes` local variable | Still in scope in `_handle_audio_chunk()`. Same Python reference — zero overhead. |
| **Deferred** (DLQ) | Minutes to hours | GCS | Each chunk uploaded to GCS immediately. DLQ entry stores `{session_id, chunk_index, gcs_path}`. |
| **Session recovery** | After instance restart | Not needed | Transcript already in Redis. Audio already in GCS. New chunks continue normally. |

---

## Per-Stage Resiliency Mechanism

| Pipeline Stage | Failure | Mechanism | Data Source on Retry |
|---|---|---|---|
| **Audio save** | Disk write fails | tenacity (2 attempts). If fails, proceed with in-memory bytes. | `audio_bytes` in scope |
| **STT primary (Groq)** | API timeout / 429 / 5xx | tenacity 3x + pybreaker + fallback chain | `audio_bytes` in scope |
| **STT returns empty** | Provider quirk | Retry once with next provider in chain | `audio_bytes` in scope |
| **STT all providers fail** | Sustained outage | Push to Redis DLQ with GCS path | GCS (deferred batch) |
| **Extraction primary (Gemini)** | API timeout / 5xx / bad JSON | tenacity 2x + pybreaker + fallback chain | `full_transcript` string (rebuilt from session) |
| **Extraction bad JSON** | LLM outputs unparseable response | `retry_if_exception_type(json.JSONDecodeError)` | Same `full_transcript` |
| **Session state loss** | Instance restart / OOM kill | Redis (Memorystore): session hash with 2hr TTL | Redis hydration on reconnect |
| **Audio loss** | Instance death before session end | Immediate per-chunk GCS upload (fire-and-forget) | GCS |
| **WS disconnect** | Client crash / network drop | Final extraction + audio save on disconnect handler. Session persists in Redis. | Redis + GCS |

---

## Implementation Plan (5-Day Sprint)

### Day 1: Redis Session Manager

**Files to modify:**
- `src/services/session_manager.py` — Replace in-memory dict with `redis.asyncio`. `HSET`/`HGET` per session with 2hr TTL.
- `src/config/settings.py` — Add `RedisConfig` (host, port, password, db, ttl)
- `config/settings.yaml` — Add `redis:` config section (uses existing Memorystore)
- `requirements.txt` — Add `redis[hiredis]>=5.0.0`

**Design:**
- Redis Hash per session: `session:{session_id}` with fields for patient, transcript_chunks, extraction, chunk_paths
- TTL of 7200s (2 hours) — covers max WS timeout (3600s) with buffer
- `ConsultationSession` is Pydantic → `model_dump_json()` / `model_validate_json()` for serialization
- Transcript chunks: Redis List (`RPUSH`) for append-only semantics

### Day 2: tenacity + pybreaker on Providers

**Files to modify:**
- `src/providers/transcription/groq_whisper.py` — `@retry` decorator on `transcribe()`
- `src/providers/transcription/openai_whisper.py` — Same
- `src/providers/extraction/gemini_gpt.py` — `@retry` decorator on `extract()`
- `src/providers/extraction/openai_gpt.py` — Same
- `src/providers/extraction/groq_gpt.py` — Same
- `src/providers/base.py` — Add `CircuitOpenError` exception
- `requirements.txt` — Add `tenacity>=8.2.0`, `pybreaker>=1.2.0`

**Configuration:**
```python
# STT providers: fast retry (real-time audio)
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=2),
    retry=retry_if_exception_type((TranscriptionError, httpx.TimeoutException)),
)

# Extraction providers: slightly longer (background, more tolerant)
@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    retry=retry_if_exception_type((ExtractionError, json.JSONDecodeError)),
)

# Circuit breaker per provider
stt_breaker = CircuitBreaker(fail_max=3, reset_timeout=30)
```

### Day 3: Provider Fallback Chains

**Files to modify:**
- `src/services/transcription_service.py` — Single provider → ordered list with circuit-breaker-aware iteration
- `src/services/extraction_service.py` — Same pattern
- `config/settings.yaml` — `provider: "groq"` → `providers: ["groq", "gemini", "openai"]`

**Pattern:**
```python
class TranscriptionService:
    async def transcribe(self, audio_bytes: bytes) -> str:
        last_error = None
        for provider in self.providers:
            try:
                return await provider.transcribe(audio_bytes)
            except (TranscriptionError, CircuitBreakerError) as e:
                last_error = e
                logger.warning(f"{provider.__class__.__name__} failed, trying next: {e}")
                continue
        raise TranscriptionError(f"All providers failed. Last: {last_error}")
```

### Day 4: GCS Immediate Upload

**Files to modify:**
- `src/services/audio_storage.py` — Add GCS client. Upload each chunk immediately (fire-and-forget). `combine_and_save()` reads from GCS.
- `src/config/settings.py` — Add `gcs_bucket` to AudioStorageConfig
- `requirements.txt` — Add `google-cloud-storage>=2.0.0`

**Design:**
```python
async def save_chunk(self, session_id, chunk_bytes, chunk_index, source):
    # Local save (for immediate STT access)
    chunk_path = await self._save_local(session_id, chunk_bytes, chunk_index, source)
    # GCS upload (non-blocking, with retry)
    gcs_path = f"{session_id}/{source}_chunk_{chunk_index:04d}.wav"
    asyncio.create_task(self._upload_to_gcs(gcs_path, chunk_bytes))
    return chunk_path
```

### Day 5: DLQ + Session Resumption + Testing

**Files to modify:**
- `src/websocket_handler.py` — Push to DLQ on all-providers-fail. Session resumption in `_handle_start_session`.
- New: `src/services/dlq_service.py` — Redis list-based DLQ
- New: `src/services/reprocessor.py` — Batch reprocessor (reads DLQ, fetches from GCS, retries STT)

**DLQ Entry:**
```json
{
    "session_id": "uuid",
    "chunk_index": 42,
    "source": "mic",
    "gcs_path": "gs://bucket/session-id/mic_chunk_0042.wav",
    "error": "All providers failed: Groq 429, Gemini 503, OpenAI timeout",
    "timestamp": "2026-02-23T10:15:00Z",
    "retry_count": 0
}
```

---

## Configuration Addition

```yaml
redis:
  host: "${REDIS_HOST:localhost}"
  port: 6379
  password: "${REDIS_PASSWORD:}"
  session_ttl_seconds: 7200

resilience:
  stt:
    providers: ["groq", "gemini", "openai"]
    retry_attempts: 3
    retry_backoff_multiplier: 0.5
    circuit_breaker_fail_max: 3
    circuit_breaker_reset_timeout: 30
  extraction:
    providers: ["gemini", "openai", "groq"]
    retry_attempts: 2
    retry_backoff_multiplier: 1.0
    circuit_breaker_fail_max: 3
    circuit_breaker_reset_timeout: 60

audio_storage:
  gcs_bucket: "${GCS_AUDIO_BUCKET:loop-scribe-audio}"
  upload_immediately: true
```

## New Dependencies

```
tenacity>=8.2.0              # Retry with exponential backoff
pybreaker>=1.2.0             # Circuit breaker per provider
redis[hiredis]>=5.0.0        # Redis client (hiredis for C-speed parsing)
google-cloud-storage>=2.0.0  # GCS for durable audio storage
```

---

## Verification

1. **Kill Cloud Run instance mid-session** → Reconnect with same session_id → Session resumes from Redis, audio in GCS
2. **Block Groq API** (firewall/mock 503) → tenacity retries 3x → pybreaker opens → falls back to Gemini → extraction continues
3. **Block ALL STT providers** → chunk pushed to DLQ → trigger reprocessor → transcript recovered from GCS audio
4. **Load test with 10 concurrent sessions** → verify Redis session state consistency and GCS upload throughput
