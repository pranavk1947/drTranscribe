#!/usr/bin/env python3
"""Mock loop-scribe backend — implements the verified FE-BE contract (Confluence v8).

Lets you test the Chrome extension end-to-end (registration, ambient/dual modes,
pause/resume, reconnect, error paths) without the real backend.

Setup:
    pip install fastapi "uvicorn[standard]"

Run:
    python tools/mock-server.py                  # listens on http://localhost:8080
    python tools/mock-server.py --port 9000

Failure-simulation flags (each tests a specific FE edge case):
    --fail-stop        never ack stop_session       -> FE must force-close after 10s
    --drop-after N     kill the WS after N chunks   -> FE must reconnect + session_resume
    --reject-doctor    GET /api/doctors/{id} -> 404 -> FE must clear cache, show Register Now
    --conflict-once    first start_session -> SESSION_ALREADY_ACTIVE
                                                   -> FE must offer "New ID + Retry"

Doctors persist to tools/mock-doctors.json across restarts (delete it to reset).
All traffic is logged to stdout so you can watch the contract in action.
"""

import argparse
import asyncio
import json
import re
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

ARGS = None  # set in __main__
STORE_PATH = Path(__file__).parent / "mock-doctors.json"
SESSION_TTL_SECONDS = 120

app = FastAPI(title="loop-scribe mock backend (contract v8)")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

def log(*parts):
    print(f"[{time.strftime('%H:%M:%S')}]", *parts, flush=True)

# ---------------------------------------------------------------- doctors ---

def _load_doctors() -> dict:
    if STORE_PATH.exists():
        try:
            return json.loads(STORE_PATH.read_text())
        except json.JSONDecodeError:
            log("WARN: mock-doctors.json corrupt, starting empty")
    return {}

DOCTORS: dict = _load_doctors()  # doctor_id -> doctor object

def _save_doctors():
    STORE_PATH.write_text(json.dumps(DOCTORS, indent=2))

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^(\+91)?[6-9]\d{9}$")

def _validate_registration(body: dict) -> dict:
    errors = {}
    for field in ("name", "phone", "email", "medical_registration_number"):
        if not str(body.get(field, "")).strip():
            errors[field] = "This field is required"
    if "email" not in errors and not EMAIL_RE.match(body["email"].strip()):
        errors["email"] = "Invalid email address"
    if "phone" not in errors and not PHONE_RE.match(
        body["phone"].strip().replace(" ", "").replace("-", "")
    ):
        errors["phone"] = "Use a 10-digit Indian mobile number (optionally +91)"
    return errors

@app.post("/api/doctors")
async def register_doctor(request: Request):
    body = await request.json()
    log("POST /api/doctors", body.get("email"))
    errors = _validate_registration(body)
    if errors:
        return JSONResponse(
            status_code=400,
            content={"error_code": "VALIDATION_ERROR", "errors": errors},
        )
    email = body["email"].strip().lower()
    existing = next((d for d in DOCTORS.values() if d["email"] == email), None)
    if existing:
        log("  -> 409 DOCTOR_ALREADY_EXISTS", existing["doctor_id"])
        return JSONResponse(
            status_code=409,
            content={"error_code": "DOCTOR_ALREADY_EXISTS", "doctor": existing},
        )
    doctor = {
        "doctor_id": f"doc_{uuid.uuid4().hex[:8]}",
        "name": body["name"].strip(),
        "phone": body["phone"].strip(),
        "email": email,
        "medical_registration_number": body["medical_registration_number"].strip(),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    DOCTORS[doctor["doctor_id"]] = doctor
    _save_doctors()
    log("  -> 201", doctor["doctor_id"])
    return JSONResponse(status_code=201, content=doctor)

@app.get("/api/doctors/lookup")  # must be declared before /{doctor_id}
async def lookup_doctor(email: str = ""):
    log("GET /api/doctors/lookup", email)
    doctor = next(
        (d for d in DOCTORS.values() if d["email"] == email.strip().lower()), None
    )
    if not doctor:
        return JSONResponse(
            status_code=404,
            content={"error_code": "DOCTOR_NOT_FOUND", "message": "No doctor with this email"},
        )
    return doctor

@app.get("/api/doctors/{doctor_id}")
async def get_doctor(doctor_id: str):
    log("GET /api/doctors/" + doctor_id)
    if ARGS.reject_doctor or doctor_id not in DOCTORS:
        return JSONResponse(
            status_code=404,
            content={"error_code": "DOCTOR_NOT_FOUND", "message": "Unknown doctor_id"},
        )
    return DOCTORS[doctor_id]

# ----------------------------------------------------------------- config ---

@app.get("/api/config")
async def get_config():
    return {"audio": {"chunk_duration_seconds": 5, "sample_rate": 16000, "channels": 1}}

@app.get("/health")
async def health():
    active = sum(1 for s in SESSIONS.values() if s["attached"])
    return {"status": "healthy", "active_sessions": active}

# -------------------------------------------------------------- websocket ---

VALID_SOURCES_FOR_MODE = {"dual": {"mic", "tab"}, "ambient": {"ambient"}}

# Staged fake extractions: each chunk advances one stage, cumulative like the
# real pipeline, so the popup/panel cards visibly fill in while you speak.
EXTRACTION_STAGES = [
    {"chief_complaint": "headache for 3 days; nausea", "diagnosis": "", "medicine": "", "advice": "", "next_steps": ""},
    {"chief_complaint": "headache for 3 days; nausea", "diagnosis": "migraine; triggered by long screen hours", "medicine": "", "advice": "", "next_steps": ""},
    {"chief_complaint": "headache for 3 days; nausea", "diagnosis": "migraine; triggered by long screen hours", "medicine": "Paracetamol 500mg twice daily", "advice": "", "next_steps": ""},
    {"chief_complaint": "headache for 3 days; nausea", "diagnosis": "migraine; triggered by long screen hours; family history of migraine", "medicine": "Paracetamol 500mg twice daily", "advice": "reduce screen time; avoid peanuts", "next_steps": "get CBC test done; follow-up in 1 week"},
]

SESSIONS: dict = {}  # appointment_id -> session dict
_conflict_armed = {"value": False}  # set from --conflict-once

def _session(appointment_id: str, mode: str, doctor_id) -> dict:
    return {
        "appointment_id": appointment_id,
        "mode": mode,
        "doctor_id": doctor_id,
        "chunks": 0,
        "stage": 0,
        "attached": True,
        "expires_at": None,  # set on detach
    }

def _error(code: str, message: str, session_id=None, chunk_id=None) -> dict:
    return {
        "type": "error",
        "error_code": code,
        "message": message,
        "session_id": session_id,
        "chunk_id": chunk_id,
    }

def _extraction_for(sess: dict) -> dict:
    return EXTRACTION_STAGES[min(sess["stage"], len(EXTRACTION_STAGES) - 1)]

def _expire_stale():
    now = time.time()
    for aid in [a for a, s in SESSIONS.items()
                if not s["attached"] and s["expires_at"] and s["expires_at"] < now]:
        log("session expired (TTL):", aid)
        del SESSIONS[aid]

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    log("WS connected")
    current: dict | None = None
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
                mtype = msg["type"]
            except (json.JSONDecodeError, KeyError):
                await ws.send_json(_error("INVALID_MESSAGE", "Malformed JSON or missing type"))
                continue
            _expire_stale()

            if mtype == "start_session":
                aid = msg.get("appointment_id")
                mode = msg.get("mode", "dual")  # default dual per contract
                doctor_id = msg.get("doctor_id")
                if not aid or mode not in VALID_SOURCES_FOR_MODE:
                    await ws.send_json(_error("INVALID_MESSAGE", "Bad appointment_id or mode"))
                    continue
                if _conflict_armed["value"]:
                    _conflict_armed["value"] = False
                    log("simulating SESSION_ALREADY_ACTIVE (--conflict-once)")
                    await ws.send_json(_error(
                        "SESSION_ALREADY_ACTIVE",
                        "A session for this appointment is already active", aid))
                    continue
                if aid in SESSIONS and SESSIONS[aid]["attached"]:
                    await ws.send_json(_error(
                        "SESSION_ALREADY_ACTIVE",
                        "A session for this appointment is already active", aid))
                    continue
                if doctor_id and doctor_id not in DOCTORS:
                    log("WARN: unknown doctor_id (accept + log):", doctor_id)
                current = _session(aid, mode, doctor_id)
                SESSIONS[aid] = current
                log(f"session_started {aid} mode={mode} doctor={doctor_id or '-'}")
                await ws.send_json({
                    "type": "session_started", "session_id": aid,
                    "workflow_id": "none", "mode": mode,
                })

            elif mtype == "audio_chunk":
                if current is None:
                    await ws.send_json(_error(
                        "NO_ACTIVE_SESSION", "No active session. Start a session first."))
                    continue
                source = msg.get("source")
                if source not in VALID_SOURCES_FOR_MODE[current["mode"]]:
                    await ws.send_json(_error(
                        "INVALID_SOURCE_FOR_MODE",
                        f"source '{source}' is not valid for {current['mode']} mode",
                        current["appointment_id"]))
                    continue
                current["chunks"] += 1
                log(f"audio_chunk #{current['chunks']} source={source} "
                    f"({len(msg.get('audio_data', ''))} b64 bytes)")
                if ARGS.drop_after and current["chunks"] == ARGS.drop_after:
                    log(f"simulating WS drop after {ARGS.drop_after} chunks (--drop-after)")
                    current["attached"] = False
                    current["expires_at"] = time.time() + SESSION_TTL_SECONDS
                    await ws.close(code=1011)
                    return
                # advance staged extraction every 2nd chunk, throttled-ish
                if current["chunks"] % 2 == 0:
                    current["stage"] += 1
                    await ws.send_json({
                        "type": "extraction_update",
                        "extraction": _extraction_for(current),
                    })

            elif mtype == "pause_session":
                if current is None:
                    await ws.send_json(_error("NO_ACTIVE_SESSION", "Nothing to pause"))
                    continue
                log("session_paused", current["appointment_id"])
                await ws.send_json({
                    "type": "session_paused", "session_id": current["appointment_id"],
                })

            elif mtype == "session_resume":
                aid = msg.get("appointment_id")
                sess = SESSIONS.get(aid)
                if sess is None:
                    await ws.send_json(_error(
                        "SESSION_NOT_FOUND", "Session expired or unknown", aid))
                    continue
                sess["attached"] = True
                sess["expires_at"] = None
                current = sess
                log(f"session_resumed {aid} (mode={sess['mode']})")
                await ws.send_json({
                    "type": "session_resumed", "session_id": aid,
                    "extraction": _extraction_for(sess),
                })

            elif mtype == "stop_session":
                if current is None:
                    await ws.send_json(_error("NO_ACTIVE_SESSION", "Nothing to stop"))
                    continue
                aid = current["appointment_id"]
                if ARGS.fail_stop:
                    log("swallowing stop_session (--fail-stop); FE should force-close in 10s")
                    continue
                current["stage"] = len(EXTRACTION_STAGES) - 1
                await ws.send_json({          # final extraction BEFORE session_stopped
                    "type": "extraction_update", "extraction": _extraction_for(current),
                })
                await ws.send_json({
                    "type": "session_stopped", "session_id": aid,
                    "chunks_processed": current["chunks"],
                })
                log(f"session_stopped {aid} chunks={current['chunks']}")
                del SESSIONS[aid]
                current = None

            else:
                await ws.send_json(_error("INVALID_MESSAGE", f"Unknown type '{mtype}'"))

    except WebSocketDisconnect:
        if current is not None and current["appointment_id"] in SESSIONS:
            current["attached"] = False
            current["expires_at"] = time.time() + SESSION_TTL_SECONDS
            log(f"WS dropped; session {current['appointment_id']} preserved "
                f"{SESSION_TTL_SECONDS}s for session_resume")
        else:
            log("WS disconnected")

# ------------------------------------------------------------------- main ---

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--fail-stop", action="store_true")
    parser.add_argument("--drop-after", type=int, default=0, metavar="N")
    parser.add_argument("--reject-doctor", action="store_true")
    parser.add_argument("--conflict-once", action="store_true")
    ARGS = parser.parse_args()
    _conflict_armed["value"] = ARGS.conflict_once
    flags = [f for f in ("fail_stop", "drop_after", "reject_doctor", "conflict_once")
             if getattr(ARGS, f)]
    log(f"mock backend on http://localhost:{ARGS.port}  "
        f"(doctors: {len(DOCTORS)}, flags: {flags or 'none'})")
    uvicorn.run(app, host="127.0.0.1", port=ARGS.port, log_level="warning")
