/**
 * Background Service Worker - Orchestration hub for drTranscribe extension
 *
 * Responsibilities:
 * 1. Doctor registration / lookup against the backend REST API
 * 2. Session lifecycle: start / pause / resume / stop in "ambient" or "dual" mode
 * 3. chrome.tabCapture streamId acquisition for dual (teleconsult) mode
 * 4. Offscreen document lifecycle (ALL audio capture — mic + tab — lives there)
 * 5. WebSocket connection to backend, with reconnect + audio buffering when
 *    the service worker is restarted or the socket drops mid-session
 * 6. Relay extraction updates to the popup and any injected content panel
 * 7. Action badge: REC (recording) / II (paused) / ! (attention needed)
 *
 * Session state is mirrored to chrome.storage.session so a terminated
 * service worker can restore the session (mode, doctor_id, appointment_id)
 * and resume via the session_resume contract.
 */

const DEFAULT_SERVER_URL = 'http://localhost:8080';
const FETCH_TIMEOUT_MS = 8000;
const STOP_ACK_TIMEOUT_MS = 10000;
const START_ACK_TIMEOUT_MS = 10000;
const MAX_RECONNECT_ATTEMPTS = 5;
const MAX_BUFFERED_CHUNKS = 24; // 5s chunks: ~2 min in ambient mode, ~1 min in dual (two sources share the cap)

let websocket = null;
let isStarting = false;        // Guard against double-click Start
let isStopping = false;
let hasOffscreenDocument = false;
let latestExtraction = {};
let lastServerHealthy = null;  // null = unknown, true/false = last health check
let reconnectAttempts = 0;
let reconnectTimer = null;
let pendingAudioChunks = [];   // Buffered while the socket is down mid-session

// Mirrored to chrome.storage.session (survives SW termination, not browser restart)
let session = {
    active: false,
    paused: false,
    pausedReason: null,        // Human-readable reason for auto-pause, if any
    mode: 'dual',              // 'dual' | 'ambient'
    appointmentId: null,
    doctorId: null,
    serverUrl: null,
    audioConfig: null,
    targetTabId: null,         // Tab being captured (dual) / panel host
    panelUnavailable: false,   // True when the host tab is a chrome:// / New Tab
                               // page where Chrome forbids panel injection
    lostCapture: { mic: false, tab: false }
};

// ─── Session State Persistence (SW restart survival) ────────────────

async function persistSession() {
    try {
        await chrome.storage.session.set({
            drtSession: { ...session, latestExtraction }
        });
    } catch (err) {
        console.warn('[BG] Failed to persist session state:', err.message);
    }
}

async function clearPersistedSession() {
    try {
        await chrome.storage.session.remove('drtSession');
    } catch {}
}

async function restoreSessionState() {
    try {
        const result = await chrome.storage.session.get('drtSession');
        const saved = result.drtSession;
        if (saved && saved.active) {
            const { latestExtraction: savedExtraction, ...savedSession } = saved;
            session = { ...session, ...savedSession };
            latestExtraction = savedExtraction || {};
            console.log('[BG] Restored session state after SW restart:', session.appointmentId, session.mode);
            if (session.paused) {
                // P1-2: the session was PAUSED when the SW died. Do not
                // reconnect here — connectWebSocket({resume:true}) sends
                // session_resume, which would unpause the server while the
                // client/offscreen stay paused (server records silence).
                // resumeSession() reconnects lazily when the doctor presses
                // Resume.
                console.log('[BG] Restored session is paused — deferring reconnect until Resume');
            } else {
                // The socket is gone after SW termination — reconnect now;
                // buffered chunks are flushed once session_resume is acked.
                scheduleReconnect(0);
            }
        }
    } catch (err) {
        console.warn('[BG] Failed to restore session state:', err.message);
    }
}

const initPromise = restoreSessionState();

// ─── Helpers ─────────────────────────────────────────────────────────

async function getServerUrl() {
    try {
        const result = await chrome.storage.local.get('serverUrl');
        return result.serverUrl || DEFAULT_SERVER_URL;
    } catch {
        return DEFAULT_SERVER_URL;
    }
}

async function getStoredDoctor() {
    try {
        const result = await chrome.storage.local.get('doctor');
        return result.doctor || null;
    } catch {
        return null;
    }
}

function generateAppointmentId() {
    return `drt-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}

/**
 * fetch with an AbortController timeout — no hanging spinners.
 */
async function fetchWithTimeout(url, options = {}, timeoutMs = FETCH_TIMEOUT_MS) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
        return await fetch(url, { ...options, signal: controller.signal });
    } finally {
        clearTimeout(timer);
    }
}

/**
 * URLs where tabCapture / script injection cannot work.
 */
function isRestrictedUrl(url) {
    if (!url) return true;
    return !/^https?:\/\//.test(url) ||
        url.startsWith('https://chromewebstore.google.com') ||
        url.startsWith('https://chrome.google.com/webstore');
}

function isStaticContentScriptUrl(url) {
    if (!url) return false;
    return /^https:\/\/meet\.google\.com\//.test(url) ||
        /^https:\/\/(app\.)?zoom\.us\//.test(url);
}

// ─── Badge ───────────────────────────────────────────────────────────

function setBadge(state) {
    try {
        if (state === 'recording') {
            chrome.action.setBadgeText({ text: 'REC' });
            chrome.action.setBadgeBackgroundColor({ color: '#d20f39' });
        } else if (state === 'paused') {
            chrome.action.setBadgeText({ text: 'II' });
            chrome.action.setBadgeBackgroundColor({ color: '#fe8019' });
        } else if (state === 'attention') {
            chrome.action.setBadgeText({ text: '!' });
            chrome.action.setBadgeBackgroundColor({ color: '#d20f39' });
        } else {
            chrome.action.setBadgeText({ text: '' });
        }
    } catch (err) {
        console.warn('[BG] Failed to set badge:', err.message);
    }
}

// ─── Popup / Content Broadcasting ───────────────────────────────────

async function buildStatus() {
    const doctor = await getStoredDoctor();
    let mode = session.mode;
    if (!session.active) {
        try {
            const stored = await chrome.storage.local.get('lastMode');
            mode = stored.lastMode || 'dual';
        } catch {}
    }
    return {
        sessionActive: session.active,
        paused: session.paused,
        pausedReason: session.pausedReason,
        mode: mode,
        appointmentId: session.appointmentId,
        doctor: doctor,
        latestExtraction: latestExtraction,
        serverHealthy: lastServerHealthy,
        lostCapture: session.lostCapture,
        panelUnavailable: session.panelUnavailable,
        isStarting: isStarting
    };
}

/**
 * Push current status to the popup (if open). Popup listens for
 * { target: 'popup', type: 'status-update' }.
 */
async function broadcastStatus() {
    const status = await buildStatus();
    chrome.runtime.sendMessage({ target: 'popup', type: 'status-update', status })
        .catch(() => {}); // Popup closed — fine, it re-renders from get-status on open
}

function broadcastError(message, code) {
    chrome.runtime.sendMessage({ target: 'popup', type: 'session-error', message, code })
        .catch(() => {});
}

function sendToContentPanel(message) {
    if (session.targetTabId) {
        chrome.tabs.sendMessage(session.targetTabId, message).catch(() => {});
    }
}

// ─── Audio Config / Health ──────────────────────────────────────────

async function fetchAudioConfig(serverUrl) {
    try {
        const response = await fetchWithTimeout(`${serverUrl}/api/config`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const config = await response.json();
        console.log('[BG] Fetched audio config:', config);
        return config.audio || { chunk_duration_seconds: 5, sample_rate: 16000, channels: 1 };
    } catch (err) {
        console.warn('[BG] Failed to fetch audio config, using defaults:', err.message);
        return { chunk_duration_seconds: 5, sample_rate: 16000, channels: 1 };
    }
}

async function checkServerHealth(serverUrl) {
    try {
        const response = await fetchWithTimeout(`${serverUrl}/health`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        lastServerHealthy = true;
        return { ok: true, data };
    } catch (err) {
        lastServerHealthy = false;
        return { ok: false, error: err.message };
    }
}

// ─── Doctor Registration ────────────────────────────────────────────

async function registerDoctor(form) {
    if (navigator.onLine === false) {
        return {
            ok: false,
            code: 'OFFLINE',
            error: 'You appear to be offline. Check your internet connection and press Retry.'
        };
    }

    const serverUrl = await getServerUrl();
    let response;
    try {
        response = await fetchWithTimeout(`${serverUrl}/api/doctors`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: form.name,
                phone: form.phone,
                email: form.email,
                medical_registration_number: form.medical_registration_number
            })
        });
    } catch (err) {
        return {
            ok: false,
            code: 'NETWORK',
            error: `Could not reach the server at ${serverUrl}. Make sure it is running (check Settings), then press Retry.`
        };
    }

    let body = {};
    try { body = await response.json(); } catch {}

    if (response.status === 201) {
        const doctor = body.doctor || body;
        await chrome.storage.local.set({ doctor });
        await chrome.storage.session.remove('registrationError').catch(() => {});
        console.log('[BG] Doctor registered:', doctor.doctor_id);
        broadcastStatus();
        return { ok: true, doctor };
    }

    if (response.status === 409) {
        // DOCTOR_ALREADY_EXISTS — body contains the existing doctor object
        const doctor = body.doctor || body;
        if (doctor && doctor.doctor_id) {
            await chrome.storage.local.set({ doctor });
            await chrome.storage.session.remove('registrationError').catch(() => {});
            console.log('[BG] Doctor already existed, recovered:', doctor.doctor_id);
            broadcastStatus();
            return { ok: true, doctor, existing: true };
        }
        return {
            ok: false,
            code: 'CONFLICT',
            error: 'An account with these details already exists, but the server did not return it. Try "Recover by email" below.'
        };
    }

    if (response.status === 400) {
        return {
            ok: false,
            code: 'VALIDATION_ERROR',
            fields: body.fields || body.errors || {},
            error: body.message || 'Some fields were rejected by the server. Fix the highlighted fields and submit again.'
        };
    }

    return {
        ok: false,
        code: 'SERVER',
        error: `Registration failed (server returned ${response.status}). Try again, or contact support if it keeps happening.`
    };
}

async function lookupDoctorByEmail(email) {
    if (navigator.onLine === false) {
        return { ok: false, code: 'OFFLINE', error: 'You appear to be offline. Check your connection and try again.' };
    }
    const serverUrl = await getServerUrl();
    try {
        const response = await fetchWithTimeout(
            `${serverUrl}/api/doctors/lookup?email=${encodeURIComponent(email)}`
        );
        if (response.status === 200) {
            const body = await response.json();
            const doctor = body.doctor || body;
            await chrome.storage.local.set({ doctor });
            broadcastStatus();
            return { ok: true, doctor };
        }
        if (response.status === 404) {
            return { ok: false, code: 'NOT_FOUND', error: 'No account found with that email. Fill in the registration form to create one.' };
        }
        return { ok: false, code: 'SERVER', error: `Lookup failed (server returned ${response.status}). Try again in a moment.` };
    } catch (err) {
        return { ok: false, code: 'NETWORK', error: `Could not reach the server at ${serverUrl}. Check Settings and try again.` };
    }
}

/**
 * Silent refresh of the cached doctor. 404 → clear cache (popup shows
 * Register Now). Network errors → keep cache, stay quiet.
 */
async function refreshDoctor() {
    const doctor = await getStoredDoctor();
    if (!doctor || !doctor.doctor_id) return { ok: true, doctor: null };
    const serverUrl = await getServerUrl();
    try {
        const response = await fetchWithTimeout(`${serverUrl}/api/doctors/${encodeURIComponent(doctor.doctor_id)}`);
        if (response.status === 200) {
            const body = await response.json();
            const fresh = body.doctor || body;
            if (fresh && fresh.doctor_id) {
                await chrome.storage.local.set({ doctor: fresh });
                return { ok: true, doctor: fresh };
            }
            return { ok: true, doctor };
        }
        if (response.status === 404) {
            console.warn('[BG] Cached doctor no longer exists on server, clearing');
            await chrome.storage.local.remove('doctor');
            broadcastStatus();
            return { ok: true, doctor: null, removed: true };
        }
        return { ok: true, doctor }; // Unexpected status — keep cache
    } catch {
        return { ok: true, doctor }; // Network error — keep cache, no user-facing error
    }
}

// ─── WebSocket Management ───────────────────────────────────────────

function buildWsUrl(serverUrl) {
    const wsProtocol = serverUrl.startsWith('https') ? 'wss' : 'ws';
    const wsHost = serverUrl.replace(/^https?:\/\//, '');
    return `${wsProtocol}://${wsHost}/ws`;
}

/**
 * Route messages from the backend to popup + content panel.
 */
function handleServerMessage(message) {
    switch (message.type) {
        case 'session_started':
            if (message.mode && message.mode !== session.mode) {
                console.warn(`[BG] Mode mismatch: client started "${session.mode}" but server echoed "${message.mode}"`);
            }
            sendToContentPanel(message);
            break;

        case 'extraction_update':
            latestExtraction = message.extraction || latestExtraction;
            persistSession();
            sendToContentPanel(message);
            chrome.runtime.sendMessage({ target: 'popup', type: 'extraction-update', extraction: latestExtraction })
                .catch(() => {});
            break;

        case 'transcription_update':
        case 'session_paused':
        case 'session_resumed':
            sendToContentPanel(message);
            broadcastStatus();
            break;

        case 'session_stopped':
            // Unsolicited server-side stop (timeout / cleanup). The solicited
            // ack during stopSession() is intercepted by its temporary
            // ws.onmessage handler and never reaches here.
            if (session.active && !isStopping) {
                console.warn('[BG] Server stopped the session unsolicited — tearing down');
                broadcastError('The server ended the session. Review the extraction before relying on it.', 'SERVER_STOPPED');
                stopSession().catch(() => {});
            }
            break;

        case 'error': {
            const code = message.code || '';
            const text = message.message || '';
            if (code === 'INVALID_SOURCE_FOR_MODE' || text.includes('INVALID_SOURCE_FOR_MODE')) {
                // Should never happen — stop cleanly, no retry loop
                console.error('[BG] INVALID_SOURCE_FOR_MODE from server — stopping session:', message);
                broadcastError('Audio routing error — the session was stopped to protect the recording. Start a new session; if this repeats, report it.', 'INVALID_SOURCE_FOR_MODE');
                stopSession().catch(() => {});
                return;
            }
            console.error('[BG] Error from backend:', message);
            sendToContentPanel(message);
            broadcastError(text || 'The server reported an error. The session is still running — Stop and restart if extractions stall.', code);
            break;
        }

        default:
            sendToContentPanel(message);
    }
}

/**
 * Connect the WebSocket and send start_session (or session_resume when
 * reconnecting). Resolves once the server acknowledges, rejects on
 * error / SESSION_ALREADY_ACTIVE / timeout.
 */
function connectWebSocket({ resume = false } = {}) {
    return new Promise((resolve, reject) => {
        const wsUrl = buildWsUrl(session.serverUrl);
        console.log(`[BG] Connecting WebSocket to ${wsUrl} (resume: ${resume})`);

        let settled = false;
        const ws = new WebSocket(wsUrl);
        websocket = ws;

        const ackTimer = setTimeout(() => {
            if (!settled) {
                settled = true;
                try { ws.close(); } catch {}
                if (websocket === ws) websocket = null;
                reject(new Error(`The server accepted the connection but never confirmed the session. Check the server logs at ${session.serverUrl}.`));
            }
        }, START_ACK_TIMEOUT_MS);

        ws.onopen = () => {
            const payload = {
                type: resume ? 'session_resume' : 'start_session',
                appointment_id: session.appointmentId,
                mode: session.mode
            };
            if (session.doctorId) payload.doctor_id = session.doctorId;
            ws.send(JSON.stringify(payload));
            console.log(`[BG] Sent ${payload.type}:`, payload.appointment_id, payload.mode);
        };

        ws.onmessage = (event) => {
            let message;
            try {
                message = JSON.parse(event.data);
            } catch (err) {
                console.error('[BG] Failed to parse WebSocket message:', err);
                return;
            }
            console.log('[BG] Received from backend:', message.type);

            if (!settled) {
                if (message.type === 'session_started' || message.type === 'session_resumed') {
                    settled = true;
                    clearTimeout(ackTimer);
                    handleServerMessage(message);
                    resolve(message);
                    return;
                }
                if (message.type === 'error') {
                    settled = true;
                    clearTimeout(ackTimer);
                    const code = message.code ||
                        ((message.message || '').includes('already active') ||
                         (message.message || '').includes('SESSION_ALREADY_ACTIVE')
                            ? 'SESSION_ALREADY_ACTIVE' : 'SERVER_ERROR');
                    try { ws.close(); } catch {}
                    if (websocket === ws) websocket = null;
                    const err = new Error(message.message || 'Server rejected the session');
                    err.code = code;
                    reject(err);
                    return;
                }
            }
            handleServerMessage(message);
        };

        ws.onerror = () => {
            if (!settled) {
                settled = true;
                clearTimeout(ackTimer);
                if (websocket === ws) websocket = null;
                reject(new Error(`Could not open a WebSocket to ${session.serverUrl}. Check the server URL in Settings and make sure the server is running.`));
            }
        };

        ws.onclose = () => {
            console.log('[BG] WebSocket closed');
            if (websocket === ws) websocket = null;
            if (session.active && !isStopping) {
                console.warn('[BG] Unexpected WebSocket close mid-session — reconnecting');
                scheduleReconnect();
            }
        };
    });
}

// ─── Reconnect (SW termination / network blip) ──────────────────────

function scheduleReconnect(delayMs) {
    if (reconnectTimer || !session.active || isStopping) return;
    if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
        console.error('[BG] Reconnect attempts exhausted — auto-pausing');
        const reason = `Lost connection to the server at ${session.serverUrl}. The session is paused — press Resume to retry, or Stop to end it.`;
        pauseSession(reason);
        broadcastError(reason, 'RECONNECT_FAILED');
        return;
    }
    const delay = delayMs !== undefined ? delayMs : Math.min(1000 * Math.pow(2, reconnectAttempts), 15000);
    reconnectTimer = setTimeout(async () => {
        reconnectTimer = null;
        if (!session.active || isStopping || (websocket && websocket.readyState === WebSocket.OPEN)) return;
        reconnectAttempts++;
        console.log(`[BG] Reconnect attempt ${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS}`);
        try {
            await connectWebSocket({ resume: true });
            reconnectAttempts = 0;
            console.log('[BG] Reconnected, flushing', pendingAudioChunks.length, 'buffered chunks');
            flushPendingAudio();
            if (!session.paused) setBadge('recording');
            broadcastStatus();
        } catch (err) {
            console.warn('[BG] Reconnect failed:', err.message);
            scheduleReconnect();
        }
    }, delay);
}

function flushPendingAudio() {
    if (!websocket || websocket.readyState !== WebSocket.OPEN) return;
    const chunks = pendingAudioChunks;
    pendingAudioChunks = [];
    for (const chunk of chunks) {
        websocket.send(JSON.stringify(chunk));
    }
}

// ─── Audio Relay ────────────────────────────────────────────────────

function sendAudioChunk(audioData, source) {
    if (!session.active || session.paused) return; // Drop while paused/idle
    const message = { type: 'audio_chunk', audio_data: audioData, source: source || 'mic' };
    if (websocket && websocket.readyState === WebSocket.OPEN) {
        websocket.send(JSON.stringify(message));
    } else {
        // Socket down mid-session (SW restart / network blip): buffer locally
        pendingAudioChunks.push(message);
        if (pendingAudioChunks.length > MAX_BUFFERED_CHUNKS) pendingAudioChunks.shift();
        scheduleReconnect();
    }
}

// ─── Offscreen Document Management ──────────────────────────────────

async function ensureOffscreenDocument() {
    if (hasOffscreenDocument) return;
    const existingContexts = await chrome.runtime.getContexts({
        contextTypes: ['OFFSCREEN_DOCUMENT'],
        documentUrls: [chrome.runtime.getURL('offscreen.html')]
    });
    if (existingContexts.length > 0) {
        hasOffscreenDocument = true;
        return;
    }
    await chrome.offscreen.createDocument({
        url: 'offscreen.html',
        reasons: ['USER_MEDIA', 'AUDIO_PLAYBACK'],
        justification: 'Capture microphone and tab audio for medical transcription'
    });
    hasOffscreenDocument = true;
    console.log('[BG] Offscreen document created');
}

async function closeOffscreenDocument() {
    try {
        await chrome.offscreen.closeDocument();
    } catch {
        // Already closed
    }
    hasOffscreenDocument = false;
}

function sendToOffscreen(message) {
    return chrome.runtime.sendMessage({ target: 'offscreen', ...message });
}

// ─── Panel Injection (any-tab support) ──────────────────────────────

/**
 * Try to inject the content panel into a normal http(s) tab.
 * Meet/Zoom tabs already have the static content script. Failure is
 * non-fatal — the popup remains the UI.
 */
async function tryInjectPanel(tabId) {
    try {
        const tab = await chrome.tabs.get(tabId);
        if (isRestrictedUrl(tab.url)) {
            console.log('[BG] Panel injection skipped (restricted URL):', tab.url);
            return false;
        }
        if (!isStaticContentScriptUrl(tab.url)) {
            await chrome.scripting.insertCSS({ target: { tabId }, files: ['content.css'] });
            await chrome.scripting.executeScript({
                target: { tabId },
                files: ['jspdf.umd.min.js', 'export.js', 'content.js']
            });
            console.log('[BG] Panel injected into tab', tabId);
        }
        return true;
    } catch (err) {
        console.log('[BG] Panel injection failed (popup remains the UI):', err.message);
        return false;
    }
}

// ─── Session Lifecycle ──────────────────────────────────────────────

async function startSession({ mode, tabId, appointmentId, freshAppointmentId, fromPanel = false } = {}) {
    await initPromise;
    if (isStarting) {
        throw new Error('A session is already starting — give it a second.');
    }
    if (session.active) {
        throw new Error('A session is already running. Stop it before starting a new one.');
    }
    isStarting = true;
    broadcastStatus();

    let wsConnected = false;
    let offscreenStarted = false;
    try {
        // 0. Registration gate — every consult must be linked to a registered
        //    doctor. This is the single enforcement point: the popup hides
        //    Start while unregistered, and the in-page panel renders this
        //    error actionably.
        const doctor = await getStoredDoctor();
        if (!doctor || !doctor.doctor_id) {
            if (fromPanel) {
                // Best-effort: surface the popup so the doctor lands on the
                // registration form (Chrome may reject this without a fresh
                // toolbar gesture — the error message covers that case).
                try { await chrome.action.openPopup(); } catch {}
            }
            const err = new Error('Register first — click the Loop Scribe icon in the toolbar and tap Register Now.');
            err.code = 'REGISTRATION_REQUIRED';
            throw err;
        }

        // 1. Resolve mode + target tab
        const stored = await chrome.storage.local.get('lastMode');
        session.mode = mode || stored.lastMode || 'dual';
        await chrome.storage.local.set({ lastMode: session.mode });

        let targetTab = null;
        if (tabId) {
            targetTab = await chrome.tabs.get(tabId).catch(() => null);
        } else {
            const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
            targetTab = tabs[0] || null;
        }
        session.targetTabId = targetTab ? targetTab.id : null;
        // Chrome forbids injecting into chrome:// pages and the New Tab page.
        // Ambient can still run (mic-only), but there's no in-page panel there
        // — the popup becomes the live-notes surface. Flag it so the popup can
        // say so instead of the doctor wondering where the panel went.
        session.panelUnavailable = !targetTab || isRestrictedUrl(targetTab.url);

        // 2. Health check first — clear error if server is down
        session.serverUrl = await getServerUrl();
        const health = await checkServerHealth(session.serverUrl);
        if (!health.ok) {
            throw new Error(`Server unreachable at ${session.serverUrl} — check the server URL in Settings and make sure the server is running.`);
        }
        session.audioConfig = await fetchAudioConfig(session.serverUrl);

        // 3. Doctor — guaranteed present by the registration gate (step 0)
        session.doctorId = doctor.doctor_id;

        // 4. Appointment id
        session.appointmentId = freshAppointmentId
            ? generateAppointmentId()
            : (appointmentId || generateAppointmentId());

        // 5. Tab capture streamId (dual mode) — must happen on the user
        //    gesture (popup click / content button) before any await-heavy work
        let streamId = null;
        if (session.mode === 'dual') {
            if (!targetTab || isRestrictedUrl(targetTab.url)) {
                const err = new Error("This page's audio can't be captured (Chrome restricts pages like chrome://, the Web Store, and PDFs). Switch to Ambient mode to record with the microphone only.");
                err.code = 'TAB_NOT_CAPTURABLE';
                throw err;
            }
            try {
                streamId = await chrome.tabCapture.getMediaStreamId({ targetTabId: targetTab.id });
            } catch (err) {
                // P1-5: a start initiated from the in-page panel does not count
                // as "invoking the extension", so tabCapture is not granted.
                // Tell the doctor the real fix instead of "switch to Ambient".
                const e = new Error(fromPanel
                    ? 'Chrome only allows tab-audio capture when the session is started from the extension itself. Click the drTranscribe toolbar icon and press Start there (or switch to Ambient mode in the popup).'
                    : "Couldn't capture this tab's audio. Switch to Ambient mode, or open the consult page in a regular tab and try again.");
                e.code = fromPanel ? 'TAB_CAPTURE_NEEDS_POPUP' : 'TAB_NOT_CAPTURABLE';
                throw e;
            }
        }

        // 6. WebSocket + start_session (waits for session_started / error)
        await connectWebSocket();
        wsConnected = true;

        // 7. Offscreen capture (mic always; tab audio in dual mode)
        await ensureOffscreenDocument();
        const captureResult = await sendToOffscreen({
            type: 'offscreen-start-capture',
            mode: session.mode,
            streamId: streamId,
            audioConfig: session.audioConfig
        });
        if (!captureResult || !captureResult.ok) {
            const name = captureResult && captureResult.name;
            if (captureResult && captureResult.which === 'mic' &&
                (name === 'NotAllowedError' || name === 'NotFoundError' || name === 'SecurityError')) {
                // Offscreen can't show the permission prompt — open helper page
                chrome.tabs.create({ url: chrome.runtime.getURL('permissions.html') }).catch(() => {});
                const err = new Error('Microphone access needed — grant it in the tab that just opened, then press Start again.');
                err.code = 'MIC_PERMISSION';
                throw err;
            }
            throw new Error(`Audio capture failed (${(captureResult && captureResult.error) || 'unknown error'}). Check your microphone and try again.`);
        }
        offscreenStarted = true;

        // 8. Session is live
        session.active = true;
        session.paused = false;
        session.pausedReason = null;
        session.lostCapture = { mic: false, tab: false };
        latestExtraction = {};
        pendingAudioChunks = [];
        reconnectAttempts = 0;
        await persistSession();
        setBadge('recording');

        // 9. Panel injection (best-effort) + notify content script
        if (session.targetTabId) {
            await tryInjectPanel(session.targetTabId);
            sendToContentPanel({ type: 'session-started', mode: session.mode });
        }

        console.log(`[BG] Session started: ${session.appointmentId} (${session.mode})`);
        broadcastStatus();
        return { ok: true, appointmentId: session.appointmentId, mode: session.mode };
    } catch (err) {
        // Clean up partial start
        if (offscreenStarted) {
            await sendToOffscreen({ type: 'offscreen-stop-capture' }).catch(() => {});
        }
        if (wsConnected && websocket) {
            try { websocket.close(); } catch {}
            websocket = null;
        }
        if (!session.active) await closeOffscreenDocument().catch(() => {});
        session.appointmentId = null;
        session.targetTabId = null;
        setBadge('idle');
        throw err;
    } finally {
        isStarting = false;
        broadcastStatus();
    }
}

/**
 * Stop the session. Keeps the socket open until session_stopped, but
 * force-closes after STOP_ACK_TIMEOUT_MS with a warning.
 */
async function stopSession() {
    if (isStopping) return { ok: true };
    isStopping = true;
    console.log('[BG] Stopping session');

    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
    const tabId = session.targetTabId;
    let stopWarning = null;

    try {
        // 1. Stop audio capture (flushes partial chunks first)
        await sendToOffscreen({ type: 'offscreen-stop-capture' }).catch(() => {});

        // 2. Send stop_session, wait for session_stopped ack (10s cap)
        if (websocket && websocket.readyState === WebSocket.OPEN) {
            const ws = websocket;
            await new Promise((resolve) => {
                let done = false;
                const finish = (warning) => {
                    if (done) return;
                    done = true;
                    if (warning) stopWarning = warning;
                    try { ws.close(); } catch {}
                    resolve();
                };
                const timer = setTimeout(() => {
                    console.warn('[BG] No session_stopped ack within 10s, force-closing');
                    finish('The server did not confirm the stop in time — the final summary may be incomplete. Check the server before relying on this consult\'s extraction.');
                }, STOP_ACK_TIMEOUT_MS);

                const prevOnMessage = ws.onmessage;
                ws.onmessage = (event) => {
                    try {
                        const msg = JSON.parse(event.data);
                        if (msg.type === 'session_stopped') {
                            console.log('[BG] Server acknowledged session stop');
                            clearTimeout(timer);
                            finish(null);
                            return;
                        }
                    } catch {}
                    if (prevOnMessage) prevOnMessage(event);
                };
                ws.onclose = () => { clearTimeout(timer); finish(stopWarning); };

                ws.send(JSON.stringify({ type: 'stop_session', appointment_id: session.appointmentId }));
                console.log('[BG] Sent stop_session, waiting for ack...');
            });
            websocket = null;
        } else if (websocket) {
            try { websocket.close(); } catch {}
            websocket = null;
        }
    } finally {
        // 3. Tear down everything regardless of ack outcome
        await closeOffscreenDocument().catch(() => {});
        session.active = false;
        session.paused = false;
        session.pausedReason = null;
        session.appointmentId = null;
        session.targetTabId = null;
        session.lostCapture = { mic: false, tab: false };
        pendingAudioChunks = [];
        reconnectAttempts = 0;
        await clearPersistedSession();
        setBadge('idle');
        if (tabId) {
            chrome.tabs.sendMessage(tabId, { type: 'session-ended' }).catch(() => {});
        }
        isStopping = false;
        broadcastStatus();
    }
    console.log('[BG] Session stopped', stopWarning ? '(no server ack)' : '(acked)');
    return { ok: true, warning: stopWarning };
}

function pauseSession(reason) {
    if (!session.active) return { ok: true };
    if (session.paused) {
        // Already paused (e.g. capture lost while paused, P2-3): still record
        // the reason, flag attention, and persist so lostCapture survives a
        // SW restart and Resume re-acquires the lost source.
        if (reason) {
            session.pausedReason = reason;
            setBadge('attention');
        }
        persistSession();
        broadcastStatus();
        return { ok: true };
    }
    if (websocket && websocket.readyState === WebSocket.OPEN) {
        websocket.send(JSON.stringify({ type: 'pause_session', appointment_id: session.appointmentId }));
    }
    session.paused = true;
    session.pausedReason = reason || null;
    sendToOffscreen({ type: 'offscreen-pause-capture' }).catch(() => {});
    setBadge(reason ? 'attention' : 'paused');
    persistSession();
    broadcastStatus();
    console.log('[BG] Session paused', reason ? `(auto: ${reason})` : '');
    return { ok: true };
}

/**
 * Resume the session. Re-acquires any capture that was lost while paused
 * (tab closed → re-capture the now-active tab; mic unplugged → retry mic),
 * and reconnects the socket if it dropped.
 */
async function resumeSession() {
    if (!session.active || !session.paused) return { ok: true };

    // 1. Make sure the socket is alive
    // P1-3: connectWebSocket({resume:true}) already sends session_resume on
    // the fresh socket — remember that so step 3 doesn't send it twice.
    let resumedViaReconnect = false;
    if (!websocket || websocket.readyState !== WebSocket.OPEN) {
        try {
            reconnectAttempts = 0;
            if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
            await connectWebSocket({ resume: true });
            resumedViaReconnect = true;
            flushPendingAudio();
        } catch (err) {
            throw new Error(`Still can't reach the server at ${session.serverUrl} — check that it's running, then press Resume again.`);
        }
    }

    // 2. Re-acquire lost capture sources
    if (session.lostCapture.tab && session.mode === 'dual') {
        const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
        const tab = tabs[0];
        if (!tab || isRestrictedUrl(tab.url)) {
            throw new Error("The current tab's audio can't be captured. Switch to the consult tab first, then press Resume.");
        }
        let streamId;
        try {
            streamId = await chrome.tabCapture.getMediaStreamId({ targetTabId: tab.id });
        } catch {
            throw new Error("Couldn't re-capture this tab's audio. Switch to the consult tab and press Resume again, or Stop the session.");
        }
        const result = await sendToOffscreen({ type: 'offscreen-restart-tab', streamId });
        if (!result || !result.ok) {
            throw new Error('Re-capturing the tab audio failed. Press Resume to try again, or Stop the session.');
        }
        session.targetTabId = tab.id;
        session.lostCapture.tab = false;
        tryInjectPanel(tab.id).catch(() => {});
    }
    if (session.lostCapture.mic) {
        const result = await sendToOffscreen({ type: 'offscreen-restart-mic' });
        if (!result || !result.ok) {
            if (result && (result.name === 'NotAllowedError' || result.name === 'NotFoundError')) {
                chrome.tabs.create({ url: chrome.runtime.getURL('permissions.html') }).catch(() => {});
                throw new Error('Microphone unavailable — reconnect it (or grant access in the tab that just opened), then press Resume.');
            }
            throw new Error('Microphone is still unavailable. Reconnect it and press Resume, or Stop the session.');
        }
        session.lostCapture.mic = false;
    }

    // 3. Tell server + offscreen to resume (skip the server message if the
    //    reconnect in step 1 already sent session_resume — P1-3)
    if (!resumedViaReconnect && websocket && websocket.readyState === WebSocket.OPEN) {
        websocket.send(JSON.stringify({ type: 'session_resume', appointment_id: session.appointmentId }));
    }
    await sendToOffscreen({ type: 'offscreen-resume-capture' }).catch(() => {});
    session.paused = false;
    session.pausedReason = null;
    setBadge('recording');
    persistSession();
    broadcastStatus();
    console.log('[BG] Session resumed');
    return { ok: true };
}

/**
 * A capture source died mid-session (tab closed/navigated, mic unplugged).
 * Auto-pause instead of silently losing audio.
 */
async function handleCaptureEnded(which) {
    if (!session.active) return;
    session.lostCapture[which] = true;
    const reason = which === 'tab'
        ? 'Patient (tab) audio was lost — the tab was closed or navigated away. Press Resume on the consult tab to re-capture, or Stop to end the session.'
        : 'Microphone was disconnected. Reconnect your mic, then press Resume — or Stop to end the session.';
    pauseSession(reason);
    broadcastError(reason, which === 'tab' ? 'TAB_CAPTURE_LOST' : 'MIC_LOST');
}

// ─── Message Handling ───────────────────────────────────────────────

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    // Ignore messages addressed to other contexts (offscreen, popup)
    if (message.target && message.target !== 'background') return false;

    switch (message.type) {
        // ── Session control (popup or content panel) ──
        case 'start-session': {
            const tabId = sender.tab ? sender.tab.id : message.tabId;
            startSession({
                mode: message.mode,
                tabId: tabId,
                appointmentId: message.appointmentId,
                freshAppointmentId: message.freshAppointmentId,
                fromPanel: !!sender.tab // In-page panel start (no toolbar invocation) — see P1-5
            })
                .then(result => sendResponse(result))
                .catch(err => sendResponse({ ok: false, error: err.message, code: err.code }));
            return true;
        }

        case 'stop-session':
            stopSession()
                .then(result => sendResponse(result))
                .catch(err => sendResponse({ ok: false, error: err.message }));
            return true;

        case 'pause-session':
            sendResponse(pauseSession());
            return false;

        case 'resume-session':
            resumeSession()
                .then(result => sendResponse(result))
                .catch(err => sendResponse({ ok: false, error: err.message }));
            return true;

        // ── Audio from offscreen ──
        case 'audio-chunk':
            // P1-1: after a SW restart this very chunk is what wakes the
            // worker — wait for restoreSessionState() so session.active is
            // accurate, otherwise the chunk is silently dropped.
            initPromise.then(() => sendAudioChunk(message.audio_data, message.source));
            return false;

        case 'capture-started':
            console.log('[BG] Offscreen capture started');
            return false;

        case 'capture-ended':
            handleCaptureEnded(message.which);
            return false;

        case 'capture-error':
            console.error('[BG] Offscreen capture error:', message.error);
            broadcastError(`Audio capture failed: ${message.error}. The session was stopped — fix the audio device and start again.`, 'CAPTURE_ERROR');
            stopSession().catch(() => {});
            return false;

        // ── Popup queries ──
        case 'get-status':
            initPromise.then(buildStatus).then(sendResponse);
            return true;

        case 'health-check':
            (async () => {
                const serverUrl = message.serverUrl || await getServerUrl();
                sendResponse(await checkServerHealth(serverUrl));
            })();
            return true;

        case 'check-active-tab':
            (async () => {
                // Prefer the tab the popup resolved (its window is unambiguous);
                // fall back to a best-effort SW-side query only if absent.
                let tab = null;
                if (message.tabId != null) {
                    tab = await chrome.tabs.get(message.tabId).catch(() => null);
                }
                if (!tab) {
                    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
                    tab = tabs[0] || null;
                }
                sendResponse({
                    capturable: tab ? !isRestrictedUrl(tab.url) : false,
                    url: tab ? tab.url : null
                });
            })();
            return true;

        case 'set-mode':
            chrome.storage.local.set({ lastMode: message.mode }).then(() => sendResponse({ ok: true }));
            return true;

        // ── Doctor registration ──
        case 'register-doctor':
            registerDoctor(message.form)
                .then(result => {
                    // Persist outcome so a reopened popup can show it (popup
                    // may be closed while the request is in flight)
                    if (!result.ok) {
                        chrome.storage.session.set({
                            registrationError: { ts: Date.now(), error: result.error, code: result.code }
                        }).catch(() => {});
                    }
                    sendResponse(result);
                })
                .catch(err => sendResponse({ ok: false, code: 'NETWORK', error: err.message }));
            return true;

        case 'lookup-doctor':
            lookupDoctorByEmail(message.email)
                .then(sendResponse)
                .catch(err => sendResponse({ ok: false, code: 'NETWORK', error: err.message }));
            return true;

        case 'refresh-doctor':
            refreshDoctor().then(sendResponse);
            return true;
    }

    return false;
});
