# Testing Guide — drTranscribe Extension (ambient/dual + registration)

This branch implements the **verified FE-BE contract** ([Confluence v8](https://loop-health.atlassian.net/wiki/spaces/ENGINEERIN/pages/1113227310)).
No deployed backend speaks that contract yet (loop-scribe PR #24 selects mode by URL, not by the
`mode` field, and has no `/api/doctors*`). Until the backend lands, test against the **mock backend**
in `tools/mock-server.py`, which implements the contract exactly — including its error codes and
failure modes.

---

## 1. One-time setup

1. **Load the extension**: `chrome://extensions` → enable *Developer mode* → *Load unpacked* →
   select the `chromeExtension/` folder. After every code change, hit the ↻ reload icon on the card.
2. **Start the mock backend** (Python 3.10+):
   ```bash
   pip install fastapi "uvicorn[standard]"
   python tools/mock-server.py          # http://localhost:8080
   ```
   The terminal logs every REST call and WS message — keep it visible; it *is* the contract test.
3. **Point the extension at it**: click the toolbar icon → Settings → server URL
   `http://localhost:8080` (this is the default).
4. Open the service-worker console for debugging: `chrome://extensions` → drTranscribe →
   *service worker* link.

Registered doctors persist in `tools/mock-doctors.json` — delete it to reset to a "fresh server".

---

## 2. Happy paths (do these first)

### A. First-time doctor, ambient (in-person) consult — on any tab
1. Open any article page. Click the toolbar icon.
2. Expect: **Register Now** prompt (no doctor yet) and **no Start button** — registration is
   required before a session can start. Register with valid details.
   - Mock terminal shows `POST /api/doctors → 201`. Popup header shows *Dr. \<name\>* and the
     session controls unlock without reopening the popup.
   - **Immediately after registering**, a one-time mic-setup tab opens and Chrome prompts for
     microphone access. Click **Allow** — the tab confirms and closes itself. This is the *only*
     time you'll see it; the grant persists for the extension origin.
3. Select **Ambient**, press **Start**. Because mic was granted during setup, recording starts
   right away — no prompt, no extra tab. (If you skipped/denied the grant, a "Enable microphone"
   banner shows in the popup; click it once.)
4. Speak for ~20s. Expect: badge `REC`, extraction cards fill progressively (mock stages them
   every 2nd chunk), terminal logs `audio_chunk … source=ambient`.
5. **Stop**. Expect terminal: final `extraction_update` *then* `session_stopped`; popup shows the
   final summary.

### B. Teleconsult, dual mode — on Google Meet
1. Join any Meet call (or open meet.google.com with a test meeting). Click icon → **Dual** → Start.
2. Expect: terminal shows interleaved `source=mic` and `source=tab` chunks; the in-page panel AND
   the popup both update; tab audio still audible.
3. Pause → terminal `session_paused`, badge `II`. Resume → `session_resumed`. Stop.

### C. Returning doctor
1. Close and reopen Chrome. Click the icon.
2. Expect: *Dr. \<name\>* shown immediately (cache), terminal shows a background
   `GET /api/doctors/{id}` refresh. No re-registration.

---

## 3. Edge-case drills

| # | Case | How to trigger | Expected |
|---|------|----------------|----------|
| 1 | Mic permission denied | `chrome://settings/content/microphone` → remove/block the extension entry → Start ambient | Permissions page opens with instructions; popup error says mic access needed; after granting, Start works |
| 2 | Dual on restricted tab | Open `chrome://extensions`, select Dual | Preemptive warning in popup; Start errors with "use Ambient" suggestion |
| 3 | Patient tab closed mid-dual | Start dual on a tab, close that tab | Auto-pause, badge `!`, popup explains; Resume re-captures the now-active tab |
| 4 | Mic unplugged mid-session | Yank a USB headset (or switch input device off) | Same auto-pause + clear message; Resume restarts mic |
| 5 | Server down at Start | Stop the mock, press Start | "Server unreachable at \<url\>…" error, Start re-enabled; no spinner hang |
| 6 | Server dies mid-session | Kill the mock during recording | Reconnect attempts; chunks buffered (cap ~24); on mock restart within 120s, `session_resume` + flush. After 120s: SESSION_NOT_FOUND → "session lost" message |
| 7 | SW killed mid-session | Record, then `chrome://serviceworker-internals` → find the extension → Stop (or wait ~30s idle with popup closed) | SW restores from `chrome.storage.session`, sends `session_resume` with mode+doctor_id, no audio gap beyond one chunk; popup reflects live state when reopened |
| 8 | Stop never acked | `python tools/mock-server.py --fail-stop` → record → Stop | FE waits 10s, force-closes, warns "final summary may be incomplete" |
| 9 | Forced WS drop | `--drop-after 4` → record | Socket dies after 4 chunks; FE reconnects + resumes seamlessly |
| 10 | Duplicate session | `--conflict-once` → Start | SESSION_ALREADY_ACTIVE error with **New ID + Retry**; retry succeeds |
| 11 | Cached doctor invalidated | `--reject-doctor` → reopen popup | Cache cleared, Register Now shown again |
| 12 | Duplicate registration (409) | Register, delete only `chrome.storage` (reload extension via `chrome://extensions` → Remove+re-add), register again with same email | "Welcome back, Dr. X" — FE self-heals from the 409 body |
| 13 | Storage wiped, recover by email | Same wipe → "Already registered? Recover by email" | `GET /api/doctors/lookup` → profile restored without re-registering |
| 14 | Offline registration | DevTools (popup) → Network → Offline → submit form | Immediate friendly error, form input preserved, no hang |
| 15 | Bad form input | Submit empty/invalid email/9-digit phone | Inline per-field errors (client-side); server 400 path: bypass client validation by editing popup.js temporarily |
| 16 | Double-click Start | Mash Start | One session; button disabled while starting |
| 17 | Popup closed mid-flow | Start, close popup immediately, reopen | Popup re-renders correct live state from `get-status` |
| 18 | Unregistered doctor consults | Skip registration → try to Start (popup hides Start while unregistered, so use the in-page panel's Start Session) | Start blocked with REGISTRATION_REQUIRED until registered |

---

## 4. Testing against the real backend (when available)

- **loop-scribe PR #24 as-is**: only **dual** mode works (connect `/ws`; `mode` field is ignored
  harmlessly). **Ambient will fail** with `INVALID_SOURCE_FOR_MODE` because PR #24 expects ambient
  on a separate `/ws/ambient` endpoint — this is the documented migration gap, not an FE bug.
- **After backend consolidation** (single `/ws` honoring `mode`, `/api/doctors*` endpoints): rerun
  §2 and §3 drills 5–13 unchanged; they're backend-behavior tests.
- The in-repo `src/` Python server predates the contract (port 8000, different message shapes) —
  don't test against it.

## 5. What can only be verified manually (no automation)

Audio quality with real voices (VAD threshold drops soft speech?), echo cancellation in dual mode
(patient audio leaking into mic channel?), Meet SPA navigation (panel survives in-call route
changes?), long-session memory (30+ min), Bluetooth headset switching, two Chrome profiles
side-by-side, and a policy-managed Chrome where mic is admin-blocked. Walk these with a real
doctor before any rollout — see `doctor-journey-simulation.md` (QA report) for the full residual
risk list.
