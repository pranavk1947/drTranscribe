/**
 * Popup - Control surface for drTranscribe
 *
 * Stateless renderer: all session state lives in the background service
 * worker (mirrored to chrome.storage.session). On open, the popup renders
 * from get-status; while open, it re-renders from status-update broadcasts.
 *
 * Surfaces:
 * - Doctor registration (required before Start; inline form, recover-by-email)
 * - Mode selector: Ambient (in-person) vs Dual (teleconsult)
 * - Start / Pause / Resume / Stop (Start hidden until registered)
 * - Live extraction cards
 * - Server URL settings + health
 */

const DEFAULT_SERVER_URL = 'http://localhost:8080';

// ─── Elements ────────────────────────────────────────────────────────

const doctorChip = document.getElementById('doctor-chip');
const errorBanner = document.getElementById('error-banner');
const errorText = document.getElementById('error-text');
const errorActionBtn = document.getElementById('error-action-btn');

const registerNudge = document.getElementById('register-nudge');
const registerNowBtn = document.getElementById('register-now-btn');
const registerForm = document.getElementById('register-form');
const regName = document.getElementById('reg-name');
const regPhone = document.getElementById('reg-phone');
const regEmail = document.getElementById('reg-email');
const regRegno = document.getElementById('reg-regno');
const regSubmitBtn = document.getElementById('reg-submit-btn');
const regCancelBtn = document.getElementById('reg-cancel-btn');
const recoverLink = document.getElementById('recover-link');
const recoverRow = document.getElementById('recover-row');
const recoverEmail = document.getElementById('recover-email');
const recoverBtn = document.getElementById('recover-btn');
const recoverError = document.getElementById('recover-error');

const micBanner = document.getElementById('mic-banner');
const micEnableBtn = document.getElementById('mic-enable-btn');

const modeButtons = Array.from(document.querySelectorAll('.popup-mode-btn'));
const dualWarning = document.getElementById('dual-warning');

const startBtn = document.getElementById('start-btn');
const pauseBtn = document.getElementById('pause-btn');
const resumeBtn = document.getElementById('resume-btn');
const stopBtn = document.getElementById('stop-btn');
const sessionLine = document.getElementById('session-line');
const panelNote = document.getElementById('panel-note');
const extractionSection = document.getElementById('extraction-section');

const serverUrlInput = document.getElementById('server-url');
const saveBtn = document.getElementById('save-btn');
const statusDot = document.getElementById('status-dot');
const statusText = document.getElementById('status-text');

let currentStatus = null;
let selectedMode = 'dual';

// ─── Messaging helpers ──────────────────────────────────────────────

function sendMessage(message) {
    return new Promise((resolve) => {
        chrome.runtime.sendMessage(message, (response) => {
            if (chrome.runtime.lastError) {
                resolve({ ok: false, error: chrome.runtime.lastError.message });
                return;
            }
            resolve(response);
        });
    });
}

// ─── Error banner ────────────────────────────────────────────────────

function showError(message, action) {
    errorText.textContent = message;
    errorBanner.style.display = 'flex';
    if (action) {
        errorActionBtn.textContent = action.label;
        errorActionBtn.style.display = '';
        errorActionBtn.onclick = action.onClick;
    } else {
        errorActionBtn.style.display = 'none';
        errorActionBtn.onclick = null;
    }
}

function clearError() {
    errorBanner.style.display = 'none';
    errorText.textContent = '';
}

// ─── Rendering ──────────────────────────────────────────────────────

function renderDoctor(doctor) {
    if (doctor && doctor.name) {
        const name = doctor.name.replace(/^dr\.?\s*/i, '');
        doctorChip.textContent = `Dr. ${name}`;
        registerNudge.style.display = 'none';
        registerForm.style.display = 'none';
    } else {
        doctorChip.textContent = '';
        if (registerForm.style.display === 'none') {
            registerNudge.style.display = '';
        }
    }
}

function renderMode(mode, sessionActive) {
    selectedMode = mode;
    modeButtons.forEach(btn => {
        btn.classList.toggle('active', btn.dataset.mode === mode);
        btn.disabled = sessionActive; // Mode is fixed once a session starts
    });
    updateDualWarning();
}

async function updateDualWarning() {
    if (selectedMode !== 'dual' || (currentStatus && currentStatus.sessionActive)) {
        dualWarning.style.display = 'none';
        return;
    }
    const tabId = await getActiveTabId();
    const result = await sendMessage({ type: 'check-active-tab', tabId });
    if (result && result.capturable === false) {
        dualWarning.textContent = "The current tab can't be audio-captured (restricted page). Open the consult tab first, or use Ambient mode.";
        dualWarning.style.display = '';
    } else {
        dualWarning.style.display = 'none';
    }
}

function renderControls(status) {
    const { sessionActive, paused, isStarting } = status;
    // Registration is required before a session can start (the background
    // enforces this with REGISTRATION_REQUIRED; here we hide Start and make
    // registration the primary action).
    const registered = !!(status.doctor && status.doctor.doctor_id);
    startBtn.style.display = (sessionActive || !registered) ? 'none' : '';
    startBtn.disabled = !!isStarting || !registered;
    startBtn.textContent = isStarting ? 'Starting…' : '▶ Start';
    pauseBtn.style.display = sessionActive && !paused ? '' : 'none';
    resumeBtn.style.display = sessionActive && paused ? '' : 'none';
    stopBtn.style.display = sessionActive ? '' : 'none';

    sessionLine.className = 'popup-session-line';
    if (sessionActive && paused) {
        sessionLine.classList.add('paused');
        sessionLine.textContent = status.pausedReason ||
            `Paused — ${status.appointmentId || ''}`;
    } else if (sessionActive) {
        sessionLine.classList.add('recording');
        sessionLine.textContent = `Recording (${status.mode}) — ${status.appointmentId || ''}`;
    } else if (!registered) {
        sessionLine.textContent = 'Register to start your first consult.';
    } else {
        sessionLine.textContent = 'No active session';
    }
}

function renderExtraction(extraction) {
    const keys = ['chief_complaint', 'diagnosis', 'medicine', 'advice', 'next_steps'];
    let hasAny = false;
    for (const key of keys) {
        const el = document.getElementById('ext-' + key);
        if (!el) continue;
        const value = extraction && extraction[key];
        if (value && String(value).trim()) {
            el.textContent = value;
            el.classList.remove('popup-card-empty');
            hasAny = true;
        } else {
            el.textContent = '—';
            el.classList.add('popup-card-empty');
        }
    }
    const active = currentStatus && currentStatus.sessionActive;
    extractionSection.style.display = (active || hasAny) ? '' : 'none';
}

function renderStatus(status) {
    currentStatus = status;
    renderDoctor(status.doctor);
    renderMode(status.mode || 'dual', status.sessionActive);
    renderControls(status);
    renderExtraction(status.latestExtraction);

    // Chrome blocks the on-page panel on chrome:// and New Tab pages. When the
    // session is running on such a tab, tell the doctor the popup IS the panel.
    if (status.sessionActive && status.panelUnavailable) {
        panelNote.textContent = "This Chrome page can't show the floating panel — your live notes appear here in the popup. Open a normal website to get the on-page panel.";
        panelNote.style.display = '';
    } else {
        panelNote.style.display = 'none';
    }
}

// ─── Registration ───────────────────────────────────────────────────

const regFields = {
    name: { input: regName, errorEl: document.getElementById('reg-name-error') },
    phone: { input: regPhone, errorEl: document.getElementById('reg-phone-error') },
    email: { input: regEmail, errorEl: document.getElementById('reg-email-error') },
    medical_registration_number: { input: regRegno, errorEl: document.getElementById('reg-regno-error') }
};

function setFieldError(field, message) {
    const f = regFields[field];
    if (!f) return;
    f.errorEl.textContent = message || '';
    f.input.classList.toggle('popup-input-invalid', !!message);
}

function clearFieldErrors() {
    Object.keys(regFields).forEach(k => setFieldError(k, ''));
    recoverError.textContent = '';
}

function validateRegistrationForm() {
    clearFieldErrors();
    const name = regName.value.trim();
    const phone = regPhone.value.trim().replace(/[\s-]/g, '');
    const email = regEmail.value.trim();
    const regno = regRegno.value.trim();
    let valid = true;

    if (!name) { setFieldError('name', 'Name is required.'); valid = false; }
    if (!phone) {
        setFieldError('phone', 'Phone is required.'); valid = false;
    } else if (!/^([6-9]\d{9}|\+91[6-9]\d{9})$/.test(phone)) {
        setFieldError('phone', 'Enter a 10-digit Indian mobile (or +91 format).'); valid = false;
    }
    if (!email) {
        setFieldError('email', 'Email is required.'); valid = false;
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
        setFieldError('email', 'Enter a valid email address.'); valid = false;
    }
    if (!regno) { setFieldError('medical_registration_number', 'Registration number is required.'); valid = false; }

    return valid ? { name, phone, email, medical_registration_number: regno } : null;
}

function saveRegDraft() {
    chrome.storage.session.set({
        regDraft: {
            name: regName.value,
            phone: regPhone.value,
            email: regEmail.value,
            regno: regRegno.value,
            open: registerForm.style.display !== 'none'
        }
    }).catch(() => {});
}

async function restoreRegDraft() {
    try {
        const { regDraft } = await chrome.storage.session.get('regDraft');
        if (regDraft) {
            regName.value = regDraft.name || '';
            regPhone.value = regDraft.phone || '';
            regEmail.value = regDraft.email || '';
            regRegno.value = regDraft.regno || '';
            if (regDraft.open) openRegisterForm();
        }
    } catch {}
}

function openRegisterForm() {
    registerNudge.style.display = 'none';
    registerForm.style.display = '';
    saveRegDraft();
}

function closeRegisterForm() {
    registerForm.style.display = 'none';
    if (!(currentStatus && currentStatus.doctor)) registerNudge.style.display = '';
    chrome.storage.session.remove('regDraft').catch(() => {});
}

registerNowBtn.addEventListener('click', () => { clearError(); openRegisterForm(); });
regCancelBtn.addEventListener('click', closeRegisterForm);
[regName, regPhone, regEmail, regRegno].forEach(input => {
    input.addEventListener('input', saveRegDraft);
});

async function submitRegistration() {
    clearError();
    const form = validateRegistrationForm();
    if (!form) return;

    if (navigator.onLine === false) {
        showError('You appear to be offline. Check your internet connection, then press Retry.', {
            label: 'Retry', onClick: submitRegistration
        });
        return;
    }

    regSubmitBtn.disabled = true;
    regSubmitBtn.textContent = 'Registering…';
    const result = await sendMessage({ type: 'register-doctor', form });
    regSubmitBtn.disabled = false;
    regSubmitBtn.textContent = 'Register';

    if (result && result.ok) {
        closeRegisterForm();
        // Re-render from background state so the session controls unlock
        // immediately (no popup reopen needed).
        await refreshStatus();
        renderDoctor(result.doctor);
        const name = (result.doctor.name || '').replace(/^dr\.?\s*/i, '');
        sessionLine.textContent = result.existing
            ? `Welcome back, Dr. ${name}! You can start a consult now.`
            : `Registered — welcome, Dr. ${name}! You can start a consult now.`;
        // One-time mic setup right after registration, so the first Start is
        // friction-free (no prompt at consult time).
        ensureMicAfterRegistration();
        return;
    }

    if (result && result.code === 'VALIDATION_ERROR') {
        const fields = result.fields || {};
        let shown = false;
        for (const [field, msg] of Object.entries(fields)) {
            if (regFields[field]) { setFieldError(field, String(msg)); shown = true; }
        }
        if (!shown) showError(result.error, null);
        return; // Form input preserved
    }

    // Network failure / server down — non-destructive, form preserved
    showError((result && result.error) || 'Registration failed for an unknown reason. Try again.', {
        label: 'Retry', onClick: submitRegistration
    });
}

regSubmitBtn.addEventListener('click', submitRegistration);

// Recover by email (storage wiped but already registered)
recoverLink.addEventListener('click', (e) => {
    e.preventDefault();
    recoverRow.style.display = recoverRow.style.display === 'none' ? '' : 'none';
});

recoverBtn.addEventListener('click', async () => {
    recoverError.textContent = '';
    const email = recoverEmail.value.trim();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
        recoverError.textContent = 'Enter a valid email address.';
        return;
    }
    recoverBtn.disabled = true;
    const result = await sendMessage({ type: 'lookup-doctor', email });
    recoverBtn.disabled = false;
    if (result && result.ok) {
        closeRegisterForm();
        // Unlock session controls without reopening the popup
        await refreshStatus();
        renderDoctor(result.doctor);
        const name = (result.doctor.name || '').replace(/^dr\.?\s*/i, '');
        sessionLine.textContent = `Welcome back, Dr. ${name}! You can start a consult now.`;
        ensureMicAfterRegistration();
    } else {
        recoverError.textContent = (result && result.error) || 'Lookup failed. Try again.';
    }
});

// ─── Mode selector ──────────────────────────────────────────────────

modeButtons.forEach(btn => {
    btn.addEventListener('click', async () => {
        if (currentStatus && currentStatus.sessionActive) return; // Fixed mid-session
        selectedMode = btn.dataset.mode;
        renderMode(selectedMode, false);
        await sendMessage({ type: 'set-mode', mode: selectedMode });
    });
});

// ─── Microphone permission (one-time) ───────────────────────────────
//
// Mic access can't be granted at install and can't be reliably prompted
// from the popup (the permission bubble closes the popup). It IS granted to
// the extension origin and persists once given, so we prompt exactly once on
// a dedicated page; the offscreen document then inherits it silently forever.

let micPermissionStatus = null; // PermissionStatus, kept for onchange

async function getMicState() {
    try {
        const status = await navigator.permissions.query({ name: 'microphone' });
        // Re-render the banner whenever the OS/Chrome flips the grant.
        if (micPermissionStatus !== status) {
            micPermissionStatus = status;
            status.onchange = () => renderMicBanner();
        }
        return status.state; // 'granted' | 'prompt' | 'denied'
    } catch {
        return 'prompt'; // Permissions API unavailable — assume not yet granted
    }
}

async function renderMicBanner() {
    const state = await getMicState();
    micBanner.style.display = state === 'granted' ? 'none' : '';
    if (state === 'denied') {
        micBanner.querySelector('.popup-mic-text').textContent =
            'Microphone is blocked for this extension. Click to see how to re-enable it.';
    }
}

/** Open the one-time mic setup page. Returns immediately. */
function openMicSetup() {
    chrome.tabs.create({ url: chrome.runtime.getURL('permissions.html') }).catch(() => {});
}

/** Called after registration: if mic isn't granted yet, set it up now so the
 *  doctor's first Start is friction-free. */
async function ensureMicAfterRegistration() {
    const state = await getMicState();
    if (state !== 'granted') {
        openMicSetup();
        renderMicBanner(); // also leave the banner as a fallback on next open
    }
}

micEnableBtn.addEventListener('click', openMicSetup);

// Re-check when the doctor returns from the permissions tab.
window.addEventListener('focus', () => renderMicBanner());

// ─── Session controls ───────────────────────────────────────────────

/**
 * Resolve the tab the doctor is actually looking at.
 *
 * This MUST run in the popup, not the background service worker: a service
 * worker has no owning window, so chrome.tabs.query({currentWindow:true})
 * there resolves to Chrome's last-focused window — which may be a different
 * window/tab than the one the doctor invoked the extension from. Querying
 * from the popup makes "currentWindow" unambiguously the popup's own window.
 */
async function getActiveTabId() {
    try {
        const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
        return tabs && tabs[0] ? tabs[0].id : null;
    } catch {
        return null; // background will fall back to its own query
    }
}

async function doStart(freshAppointmentId) {
    clearError();
    startBtn.disabled = true; // Double-click guard (background also guards)
    startBtn.textContent = 'Starting…';

    const tabId = await getActiveTabId();
    const result = await sendMessage({
        type: 'start-session',
        mode: selectedMode,
        tabId: tabId,
        freshAppointmentId: !!freshAppointmentId
    });

    if (result && result.ok) {
        // status-update broadcast re-renders; do a refresh just in case
        refreshStatus();
        return;
    }

    startBtn.disabled = false;
    startBtn.textContent = '▶ Start';

    const code = result && result.code;
    const message = (result && result.error) || 'Could not start the session. Try again.';
    if (code === 'REGISTRATION_REQUIRED') {
        // Shouldn't normally happen (Start is hidden while unregistered) —
        // defensive path if state drifted while the popup was open.
        refreshStatus();
        showError(message, {
            label: 'Register',
            onClick: () => { clearError(); openRegisterForm(); }
        });
    } else if (code === 'SESSION_ALREADY_ACTIVE') {
        showError('A session for this appointment is already active on the server. Start with a fresh appointment ID?', {
            label: 'New ID + Retry',
            onClick: () => doStart(true)
        });
    } else if (code === 'TAB_NOT_CAPTURABLE') {
        showError(message, {
            label: 'Use Ambient',
            onClick: async () => {
                clearError();
                selectedMode = 'ambient';
                renderMode('ambient', false);
                await sendMessage({ type: 'set-mode', mode: 'ambient' });
            }
        });
    } else {
        showError(message, { label: 'Retry', onClick: () => doStart(false) });
    }
}

startBtn.addEventListener('click', () => doStart(false));

pauseBtn.addEventListener('click', async () => {
    clearError();
    await sendMessage({ type: 'pause-session' });
    refreshStatus();
});

resumeBtn.addEventListener('click', async () => {
    clearError();
    resumeBtn.disabled = true;
    resumeBtn.textContent = 'Resuming…';
    const result = await sendMessage({ type: 'resume-session' });
    resumeBtn.disabled = false;
    resumeBtn.textContent = '▶ Resume';
    if (!result || !result.ok) {
        showError((result && result.error) || 'Could not resume. Try again or stop the session.', null);
    }
    refreshStatus();
});

stopBtn.addEventListener('click', async () => {
    clearError();
    stopBtn.disabled = true;
    stopBtn.textContent = 'Stopping…';
    const result = await sendMessage({ type: 'stop-session' });
    stopBtn.disabled = false;
    stopBtn.textContent = '■ Stop';
    if (result && result.warning) {
        showError(result.warning, null);
    }
    refreshStatus();
});

// ─── Settings / health ──────────────────────────────────────────────

function setHealthStatus(state, text) {
    statusText.textContent = text;
    statusDot.className = 'popup-status-dot popup-status-' + state;
}

function checkHealth() {
    const url = serverUrlInput.value.trim().replace(/\/+$/, '');
    setHealthStatus('checking', 'Checking...');
    sendMessage({ type: 'health-check', serverUrl: url }).then((response) => {
        if (response && response.ok) {
            setHealthStatus('ok', 'Connected');
        } else {
            setHealthStatus('error', (response && response.error) || 'Unreachable');
        }
    });
}

saveBtn.addEventListener('click', () => {
    const url = serverUrlInput.value.trim().replace(/\/+$/, '');
    if (!url) {
        serverUrlInput.value = DEFAULT_SERVER_URL;
        return;
    }
    chrome.storage.local.set({ serverUrl: url }, () => {
        saveBtn.textContent = 'Saved!';
        setTimeout(() => { saveBtn.textContent = 'Save'; }, 1500);
        checkHealth();
    });
});

// ─── Live updates from background ───────────────────────────────────

chrome.runtime.onMessage.addListener((message) => {
    if (message.target !== 'popup') return;
    switch (message.type) {
        case 'status-update':
            renderStatus(message.status);
            break;
        case 'extraction-update':
            renderExtraction(message.extraction);
            break;
        case 'session-error':
            showError(message.message, null);
            break;
    }
});

// ─── Init ───────────────────────────────────────────────────────────

async function refreshStatus() {
    const status = await sendMessage({ type: 'get-status' });
    if (status && typeof status.sessionActive === 'boolean') {
        renderStatus(status);
    }
}

(async function init() {
    // Settings
    chrome.storage.local.get(['serverUrl'], (result) => {
        serverUrlInput.value = result.serverUrl || DEFAULT_SERVER_URL;
        checkHealth();
    });

    // Render from authoritative background state
    await refreshStatus();

    // Show the one-time mic banner if access isn't granted yet (hidden once it is)
    renderMicBanner();

    // Surface a registration outcome that completed while the popup was closed
    try {
        const { registrationError } = await chrome.storage.session.get('registrationError');
        if (registrationError && Date.now() - registrationError.ts < 10 * 60 * 1000) {
            showError(registrationError.error, { label: 'Retry', onClick: () => { clearError(); openRegisterForm(); } });
            chrome.storage.session.remove('registrationError').catch(() => {});
        }
    } catch {}

    // Restore a half-typed registration form (popup closed mid-entry)
    if (!(currentStatus && currentStatus.doctor)) {
        await restoreRegDraft();
    }

    // Silent server-side doctor refresh (404 clears cache; network errors keep it)
    if (currentStatus && currentStatus.doctor) {
        sendMessage({ type: 'refresh-doctor' }).then((result) => {
            if (result && result.removed) {
                renderDoctor(null);
                showError('Your registration was not found on the server — it may have been reset. Please register again.', {
                    label: 'Register', onClick: () => { clearError(); openRegisterForm(); }
                });
            } else if (result && result.doctor) {
                renderDoctor(result.doctor);
            }
        });
    }
})();
