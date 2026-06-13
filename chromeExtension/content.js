/**
 * Content Script - Loop Scribe in-page floating panel (pure UI)
 *
 * Statically injected on Google Meet / Zoom Web Client; programmatically
 * injected (chrome.scripting) on any other http(s) tab when a session
 * starts from the popup.
 *
 * All audio capture lives in the offscreen document — this script only
 * renders the panel, relays control clicks to the background, and shows
 * extraction updates.
 *
 * Panel state machine: ready -> recording <-> paused -> completed -> ready
 * - ready:     primary "Start Session"; cards show "Waiting for session..."
 * - recording: primary "Pause"; outlined "End Session"; empty cards "Listening..."
 * - paused:    primary "Resume"; outlined "End Session"
 * - completed: primary "Start New Session"; cards contenteditable (local
 *              edits only); lime "Copy to EMR" + PDF link below the cards
 *
 * Minimize: the "—" button hides the window and shows a circular Loop ring
 * badge (bottom-right). The same badge is the launcher on Meet/Zoom before
 * the panel is first opened — the two never coexist with the window.
 * Restoring toggles visibility only; the panel is never rebuilt.
 */
(function () {
    'use strict';

    // Prevent double-injection (static + programmatic can overlap)
    if (window.__drtContentLoaded) return;
    window.__drtContentLoaded = true;

    // ─── Platform Detection ────────────────────────────────────

    function isMeetingUrl(pathname, hostname) {
        // Google Meet: /abc-defg-hij
        if (hostname.includes('meet.google.com')) {
            return /^\/[a-z]{3}-[a-z]{4}-[a-z]{3}/.test(pathname);
        }
        // Zoom Web Client: /wc/123456 or /j/123456
        if (hostname.includes('zoom.us')) {
            return /^\/(wc|j)\/\d+/.test(pathname);
        }
        return false;
    }

    const onMeetingPlatform = window.location.hostname.includes('meet.google.com') ||
        window.location.hostname.includes('zoom.us');

    if (isMeetingUrl(window.location.pathname, window.location.hostname)) {
        injectBadge();
    } else if (onMeetingPlatform) {
        // Watch for SPA navigation into a meeting
        let lastPath = window.location.pathname;
        const observer = new MutationObserver(() => {
            if (window.location.pathname !== lastPath) {
                lastPath = window.location.pathname;
                if (isMeetingUrl(lastPath, window.location.hostname) && !document.getElementById('drt-badge')) {
                    injectBadge();
                }
            }
        });
        observer.observe(document.body, { childList: true, subtree: true });
    }
    // On any other page (programmatic injection), the badge + panel appear
    // when the background sends session-started.

    // ─── State ─────────────────────────────────────────────────

    let panelState = 'ready';        // 'ready' | 'recording' | 'paused' | 'completed'
    let isMinimized = false;         // Per-tab, in-memory minimized flag
    let currentPatient = { name: '', age: '', gender: '' };
    let latestExtraction = {};
    let appointmentData = null;      // Received appointment/patient data (via postMessage)

    // NOTE: Mic capture lives in the offscreen document (offscreen.js).
    // This script is pure UI — it never touches getUserMedia.

    const FIELDS = [
        { key: 'chief_complaint', label: 'Chief Complaint', icon: '&#x1FA7A;', accent: 'chief' },
        { key: 'diagnosis', label: 'Diagnosis', icon: '&#x1F4CB;', accent: 'diagnosis' },
        { key: 'medicine', label: 'Medicine', icon: '&#x1F48A;', accent: 'medicine' },
        { key: 'advice', label: 'Advice', icon: '&#x1F4AC;', accent: 'advice' },
        { key: 'next_steps', label: 'Next Steps', icon: '&#x27A1;', accent: 'nextsteps' }
    ];

    const STATUS_META = {
        ready: { label: 'Ready', dot: 'drt-dot-grey' },
        recording: { label: 'Recording', dot: 'drt-dot-green drt-dot-pulse' },
        paused: { label: 'Paused', dot: 'drt-dot-amber' },
        completed: { label: 'Completed', dot: 'drt-dot-green' }
    };

    // ─── Minimize Badge ────────────────────────────────────────

    function injectBadge() {
        if (document.getElementById('drt-badge')) return;
        const badge = document.createElement('div');
        badge.id = 'drt-badge';
        badge.className = 'drt-badge';
        badge.title = 'Loop Scribe — click to open';
        // Loop ring mark in pure CSS (dark green disc + lime ring)
        badge.innerHTML = '<span class="drt-badge-ring"></span><span class="drt-badge-dot" id="drt-badge-dot"></span>';

        badge.addEventListener('click', () => {
            // Open the panel FIRST and unconditionally — never gate the UI on
            // the EMR handshake (on Meet/Zoom there's no opener, and any hiccup
            // there must not leave the badge doing nothing).
            restorePanel();
            if (!badge.dataset.emrRequested) {
                badge.dataset.emrRequested = '1';
                requestPatientDataFromEMR().catch(() => {});
            }
        });
        document.body.appendChild(badge);
        updateBadge();
    }

    /** Hide the window, show the badge (state stays intact). */
    function minimizePanel() {
        const panel = document.getElementById('drt-panel');
        if (panel) panel.style.display = 'none';
        isMinimized = true;
        if (!document.getElementById('drt-badge')) injectBadge();
        const badge = document.getElementById('drt-badge');
        if (badge) badge.style.display = '';
        updateBadge();
    }

    /** Show the window (creating it once if needed), hide the badge. */
    function restorePanel() {
        if (!document.getElementById('drt-panel')) injectPanel();
        const panel = document.getElementById('drt-panel');
        if (panel) panel.style.display = 'flex';
        isMinimized = false;
        const badge = document.getElementById('drt-badge');
        if (badge) badge.style.display = 'none';
    }

    /** Status dot overlay on the badge mirrors the session state. */
    function updateBadge() {
        const dot = document.getElementById('drt-badge-dot');
        if (!dot) return;
        dot.className = 'drt-badge-dot';
        if (panelState === 'recording') dot.classList.add('drt-badge-dot-recording');
        else if (panelState === 'paused') dot.classList.add('drt-badge-dot-paused');
        else if (panelState === 'completed') dot.classList.add('drt-badge-dot-completed');
    }

    /** Subtle pulse when new data arrives while minimized (no auto-expand). */
    function pulseBadge() {
        const badge = document.getElementById('drt-badge');
        if (!badge || badge.style.display === 'none') return;
        badge.classList.remove('drt-badge-blip');
        void badge.offsetWidth; // restart the animation
        badge.classList.add('drt-badge-blip');
    }

    // ─── Panel ─────────────────────────────────────────────────

    function injectPanel() {
        if (document.getElementById('drt-panel')) return;

        const panel = document.createElement('div');
        panel.id = 'drt-panel';
        panel.className = 'drt-panel';

        const cardsHtml = FIELDS.map(f => `
                    <div class="drt-card drt-card-${f.accent}">
                        <div class="drt-card-header">
                            <span class="drt-card-chip">${f.icon}</span>
                            <span class="drt-card-title">${f.label}</span>
                        </div>
                        <div class="drt-card-body drt-empty" id="drt-field-${f.key}">Waiting for session to begin...</div>
                    </div>`).join('');

        panel.innerHTML = `
            <div class="drt-header" id="drt-header">
                <img class="drt-wordmark" src="${chrome.runtime.getURL('icons/logo.png')}" alt="Loop" />
                <span class="drt-statusline">
                    <span class="drt-status-dot drt-dot-grey" id="drt-status-dot"></span>
                    <span id="drt-status-label">Ready</span>
                </span>
                <button class="drt-btn-min" id="drt-minimize" title="Minimize">&#x2014;</button>
            </div>

            <div class="drt-error" id="drt-error" style="display: none;">
                <span id="drt-error-text"></span>
            </div>

            <div class="drt-body" id="drt-body">
                <button class="drt-btn-primary" id="drt-primary-btn">&#x25B6; Start Session</button>
                <div class="drt-hint" id="drt-hint" style="display: none;">You can make edits after the session ends</div>

                <div class="drt-cards" id="drt-cards">${cardsHtml}
                </div>

                <button class="drt-btn-end" id="drt-end-btn" style="display: none;">&#x25A0; End Session</button>

                <div class="drt-complete-actions" id="drt-complete-actions" style="display: none;">
                    <button class="drt-btn-copy" id="drt-copy-btn">Copy to EMR</button>
                    <a href="#" class="drt-pdf-link" id="drt-pdf-link">Download PDF</a>
                </div>
            </div>

            <div class="drt-footer">Loop Scribe v1.0 &middot; HIPAA Compliant</div>
        `;

        document.body.appendChild(panel);
        setupPanelBehavior();
        renderState();
    }

    function setupPanelBehavior() {
        const panel = document.getElementById('drt-panel');
        const header = document.getElementById('drt-header');
        const minimizeBtn = document.getElementById('drt-minimize');
        const primaryBtn = document.getElementById('drt-primary-btn');
        const endBtn = document.getElementById('drt-end-btn');
        const copyBtn = document.getElementById('drt-copy-btn');
        const pdfLink = document.getElementById('drt-pdf-link');

        // ─── Dragging ──────────────────────────────────────
        let isDragging = false;
        let dragOffsetX = 0;
        let dragOffsetY = 0;

        header.addEventListener('mousedown', (e) => {
            if (e.target.closest('button')) return;
            isDragging = true;
            dragOffsetX = e.clientX - panel.offsetLeft;
            dragOffsetY = e.clientY - panel.offsetTop;
            panel.style.transition = 'none';
        });

        document.addEventListener('mousemove', (e) => {
            if (!isDragging) return;
            e.preventDefault();
            const x = Math.max(0, Math.min(window.innerWidth - panel.offsetWidth, e.clientX - dragOffsetX));
            const y = Math.max(0, Math.min(window.innerHeight - panel.offsetHeight, e.clientY - dragOffsetY));
            panel.style.left = x + 'px';
            panel.style.top = y + 'px';
            panel.style.right = 'auto';
        });

        document.addEventListener('mouseup', () => {
            isDragging = false;
            panel.style.transition = '';
        });

        // ─── Minimize to badge ─────────────────────────────
        minimizeBtn.addEventListener('click', minimizePanel);

        // ─── Primary button (state-dependent) ──────────────
        primaryBtn.addEventListener('click', () => {
            if (panelState === 'ready') {
                doStartSession();
            } else if (panelState === 'recording') {
                doPause();
            } else if (panelState === 'paused') {
                doResume();
            } else if (panelState === 'completed') {
                startNewSession();
            }
        });

        // ─── End Session ───────────────────────────────────
        endBtn.addEventListener('click', doEndSession);

        // ─── Copy to EMR (completed state) ─────────────────
        copyBtn.addEventListener('click', doCopyToEMR);

        // ─── PDF export (secondary link, completed state) ──
        pdfLink.addEventListener('click', async (e) => {
            e.preventDefault();
            const settings = await chrome.storage.local.get(['doctorName', 'clinicName', 'doctor']);
            window.DrTExport.exportPDF(currentPatient, {
                doctorName: (settings.doctor && settings.doctor.name) || settings.doctorName || '',
                clinicName: settings.clinicName || ''
            });
        });
    }

    // ─── Session Actions ───────────────────────────────────────

    function doStartSession() {
        clearPanelError();

        // Patient details come from the EMR handshake when available; the
        // background ignores the patient payload (kept for contract compat).
        let name = '', age = '', gender = '';
        let appointmentId = null;
        let history = null;
        if (appointmentData && appointmentData.patient) {
            name = appointmentData.patient.name || '';
            age = appointmentData.patient.age || '';
            gender = appointmentData.patient.gender || '';
            appointmentId = appointmentData.appointmentId || null;
            history = appointmentData.patient.history || null;
        }
        currentPatient = { name, age, gender };

        setPrimaryBusy(true);
        setStatusLine('Connecting…', 'drt-dot-amber drt-dot-pulse');

        const payload = {
            type: 'start-session',
            patient: { name, age, gender }
        };
        if (appointmentId) payload.appointmentId = appointmentId;
        if (history) payload.history = history;

        chrome.runtime.sendMessage(payload, (response) => {
            setPrimaryBusy(false);
            if (chrome.runtime.lastError) {
                renderState();
                showPanelError('Extension error: ' + chrome.runtime.lastError.message);
                return;
            }
            if (response && response.ok) {
                // session-started message updates the UI
            } else {
                renderState();
                // REGISTRATION_REQUIRED / TAB_CAPTURE_NEEDS_POPUP messages are
                // already actionable ("click the toolbar icon ...") — render
                // them verbatim in the banner.
                showPanelError((response && response.error) || 'Could not start the session. Try again.');
            }
        });
    }

    function doPause() {
        clearPanelError();
        setState('paused'); // Optimistic — server session_paused confirms
        chrome.runtime.sendMessage({ type: 'pause-session' });
    }

    function doResume() {
        clearPanelError();
        const primaryBtn = document.getElementById('drt-primary-btn');
        if (primaryBtn) primaryBtn.disabled = true;
        setStatusLine('Reconnecting…', 'drt-dot-amber drt-dot-pulse');
        chrome.runtime.sendMessage({ type: 'resume-session' }, (response) => {
            if (primaryBtn) primaryBtn.disabled = false;
            if (chrome.runtime.lastError || !response || !response.ok) {
                renderState(); // Back to Paused
                showPanelError((response && response.error) ||
                    (chrome.runtime.lastError && chrome.runtime.lastError.message) ||
                    'Could not resume the session. Try again or end the session.');
                return;
            }
            setState('recording');
        });
    }

    function doEndSession() {
        clearPanelError();
        const endBtn = document.getElementById('drt-end-btn');
        if (endBtn) { endBtn.disabled = true; endBtn.textContent = 'Ending…'; }
        chrome.runtime.sendMessage({ type: 'stop-session' }, (response) => {
            if (endBtn) { endBtn.disabled = false; endBtn.innerHTML = '&#x25A0; End Session'; }
            if (response && response.warning) {
                showToast(response.warning);
            }
            // session-ended message drives the state change to completed
        });
    }

    /** Completed → start the next consult (resets cards, then starts). */
    function startNewSession() {
        latestExtraction = {};
        const copyBtn = document.getElementById('drt-copy-btn');
        if (copyBtn) {
            copyBtn.innerHTML = 'Copy to EMR';
            copyBtn.classList.remove('drt-copied');
        }
        setState('ready');
        doStartSession();
    }

    // ─── Copy to EMR ───────────────────────────────────────────

    function getEditedFields() {
        const data = {};
        for (const f of FIELDS) {
            const el = document.getElementById('drt-field-' + f.key);
            data[f.key] = el ? (el.innerText || '').trim() : '';
        }
        return data;
    }

    function doCopyToEMR() {
        const copyBtn = document.getElementById('drt-copy-btn');
        const extraction = getEditedFields();

        // Formatted plain-text summary to the clipboard (DrTExport reads the
        // edited drt-field-* values)
        const ok = window.DrTExport ? window.DrTExport.exportClipboard(currentPatient) : false;

        // Best-effort: also push to a connected EMR page (existing flow)
        const sentToEmr = exportToEMR(extraction);
        if (sentToEmr) showToast('Also sent to the connected EMR page');

        if (ok !== false) {
            if (copyBtn) {
                copyBtn.innerHTML = '&#x2713; Copied to EMR';
                copyBtn.classList.add('drt-copied');
                setTimeout(() => {
                    copyBtn.innerHTML = 'Copy to EMR';
                    copyBtn.classList.remove('drt-copied');
                }, 2500);
            }
        } else {
            showToast('Copy failed — select the text and copy manually');
        }
    }

    // ─── State Rendering ───────────────────────────────────────

    function setState(state) {
        panelState = state;
        renderState();
    }

    function setStatusLine(label, dotClasses) {
        const dot = document.getElementById('drt-status-dot');
        const lab = document.getElementById('drt-status-label');
        if (lab) lab.textContent = label;
        if (dot) dot.className = 'drt-status-dot ' + (dotClasses || 'drt-dot-grey');
    }

    function setPrimaryBusy(busy) {
        const primaryBtn = document.getElementById('drt-primary-btn');
        if (primaryBtn) primaryBtn.disabled = busy;
    }

    function renderState() {
        const meta = STATUS_META[panelState] || STATUS_META.ready;
        setStatusLine(meta.label, meta.dot);

        const primaryBtn = document.getElementById('drt-primary-btn');
        const hint = document.getElementById('drt-hint');
        const endBtn = document.getElementById('drt-end-btn');
        const completeActions = document.getElementById('drt-complete-actions');
        if (!primaryBtn) return; // Panel not built yet

        if (panelState === 'recording') {
            primaryBtn.innerHTML = '&#x23F8; Pause';
        } else if (panelState === 'paused') {
            primaryBtn.innerHTML = '&#x25B6; Resume';
        } else if (panelState === 'completed') {
            primaryBtn.innerHTML = '&#x25B6; Start New Session';
        } else {
            primaryBtn.innerHTML = '&#x25B6; Start Session';
        }
        primaryBtn.disabled = false;

        const mid = panelState === 'recording' || panelState === 'paused';
        if (hint) hint.style.display = mid ? '' : 'none';
        if (endBtn) endBtn.style.display = mid ? '' : 'none';
        if (completeActions) completeActions.style.display = panelState === 'completed' ? '' : 'none';

        setCardsEditable(panelState === 'completed');
        renderExtraction();
        updateBadge();
    }

    /**
     * Completed: cards become locally editable (plaintext). On entering the
     * state each field is seeded once from the latest extraction; after that
     * the DOM is the source of truth so edits are never clobbered.
     */
    function setCardsEditable(editable) {
        for (const f of FIELDS) {
            const el = document.getElementById('drt-field-' + f.key);
            if (!el) continue;
            const isEditable = el.classList.contains('drt-editable');
            if (editable && !isEditable) {
                const value = latestExtraction && latestExtraction[f.key];
                el.textContent = (value && String(value).trim()) ? String(value).trim() : '';
                el.classList.remove('drt-empty');
                el.setAttribute('contenteditable', 'plaintext-only');
                el.classList.add('drt-editable');
            } else if (!editable && isEditable) {
                el.removeAttribute('contenteditable');
                el.classList.remove('drt-editable');
            }
        }
    }

    function renderExtraction() {
        if (panelState === 'completed') return; // Fields are user-editable now
        const listening = panelState === 'recording' || panelState === 'paused';
        for (const f of FIELDS) {
            const el = document.getElementById('drt-field-' + f.key);
            if (!el) continue;
            const value = latestExtraction && latestExtraction[f.key];
            if (value && String(value).trim()) {
                el.textContent = value;
                el.classList.remove('drt-empty');
            } else {
                el.textContent = listening ? 'Listening...' : 'Waiting for session to begin...';
                el.classList.add('drt-empty');
            }
        }
    }

    // ─── Error Banner ──────────────────────────────────────────

    function showPanelError(message) {
        const banner = document.getElementById('drt-error');
        const text = document.getElementById('drt-error-text');
        if (!banner || !text) return;
        text.textContent = message;
        banner.style.display = '';
    }

    function clearPanelError() {
        const banner = document.getElementById('drt-error');
        if (banner) banner.style.display = 'none';
    }

    // ─── Toast Notification ────────────────────────────────────

    function showToast(message) {
        const existing = document.getElementById('drt-toast');
        if (existing) existing.remove();

        const toast = document.createElement('div');
        toast.id = 'drt-toast';
        toast.className = 'drt-toast';
        toast.textContent = message;
        document.body.appendChild(toast);

        requestAnimationFrame(() => {
            toast.classList.add('drt-toast-visible');
        });

        setTimeout(() => {
            toast.classList.remove('drt-toast-visible');
            setTimeout(() => toast.remove(), 300);
        }, 2000);
    }

    // ─── Messages from Background ──────────────────────────────

    chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
        switch (message.type) {
            case 'session-started':
                // Session may have been started from the popup on a page where
                // the badge/panel don't exist yet (programmatic injection).
                if (!document.getElementById('drt-badge')) injectBadge();
                restorePanel(); // Direct user action — expanding is expected
                latestExtraction = {};
                clearPanelError();
                setState('recording');
                break;

            case 'session-ended':
                if (panelState === 'recording' || panelState === 'paused') {
                    setState('completed');
                }
                if (message.reason) {
                    console.warn('[drT] Session ended:', message.reason);
                }
                break;

            case 'session_paused':
                // Accept from any live state — a freshly injected panel (tab
                // re-capture after loss) starts in 'ready' but the session is
                // server-confirmed paused.
                if (panelState !== 'completed') {
                    setState('paused');
                }
                console.log('[drT] Session paused (server confirmed)');
                break;

            case 'session_resumed':
                if (message.extraction) {
                    latestExtraction = message.extraction;
                }
                if (panelState !== 'completed') {
                    setState('recording');
                }
                console.log('[drT] Session resumed (server confirmed)');
                break;

            case 'extraction_update':
                latestExtraction = message.extraction || latestExtraction;
                renderExtraction();
                if (isMinimized) pulseBadge(); // Subtle nudge, no auto-expand
                break;

            case 'error':
                console.error('[drT] Error from backend:', message.message);
                showPanelError(message.message || 'The server reported an error.');
                if (isMinimized) pulseBadge();
                break;
        }
        return false;
    });

    // ─── Cross-Tab Communication via postMessage ────────────────────

    /**
     * Initialize message listener for cross-tab communication with EMR page
     */
    function initMessageListener() {
        window.addEventListener('message', (event) => {
            // Verify message is from drTranscribe EMR
            if (event.data && event.data.source === 'drTranscribe-EMR') {
                console.log('[drT PostMessage] Received from EMR:', event.data);
                handlePatientDataResponse(event.data);
            }
        });
        console.log('[drT PostMessage] Listener initialized');
    }

    /**
     * Request patient data from EMR page via window.opener
     * Called when user clicks badge for the first time
     * Returns a promise that resolves when data is received or times out
     */
    async function requestPatientDataFromEMR() {
        if (!window.opener || window.opener.closed) {
            console.log('[drT PostMessage] No opener window available, skipping EMR request');
            return;
        }

        console.log('[drT PostMessage] Requesting patient data from EMR...');

        // Send request to opener (EMR demo page)
        try {
            window.opener.postMessage({
                type: 'request-patient-data',
                source: 'drTranscribe-Extension',
                timestamp: new Date().toISOString()
            }, '*'); // Allow any origin for now
        } catch (err) {
            console.warn('[drT PostMessage] Failed to send request:', err.message);
            return;
        }

        // Wait for response with timeout (2 seconds)
        await new Promise(resolve => setTimeout(resolve, 2000));

        if (appointmentData) {
            console.log('[drT PostMessage] Patient data received from EMR');
        } else {
            console.log('[drT PostMessage] No patient data received (timeout or no EMR page)');
        }
    }

    /**
     * Handle patient-data-response message from EMR page
     * Stores appointmentData for use in session and export
     */
    function handlePatientDataResponse(data) {
        console.log('[drT PostMessage] Patient data received:', data);

        // Store appointment data for use in session start and export
        appointmentData = data;
        if (data.patient) {
            currentPatient = {
                name: data.patient.name || '',
                age: data.patient.age || '',
                gender: data.patient.gender || ''
            };
        }
    }

    /**
     * Export extraction results back to EMR page via postMessage
     * Called after session ends from Copy to EMR (best-effort)
     */
    function exportToEMR(extraction) {
        if (!window.opener || window.opener.closed) {
            console.warn('[drT PostMessage] Opener window not available');
            return false;
        }

        if (!appointmentData) {
            console.warn('[drT PostMessage] No appointment data available');
            return false;
        }

        try {
            window.opener.postMessage({
                type: 'export-to-emr',
                source: 'drTranscribe-Extension',
                appointmentId: appointmentData.appointmentId,
                extractedData: extraction
            }, '*');

            console.log('[drT PostMessage] Results sent to EMR page');
            return true;
        } catch (err) {
            console.error('[drT PostMessage] Failed to send results:', err);
            return false;
        }
    }

    // Initialize message listener immediately when content script loads
    // This ensures the listener is ready to receive messages from EMR demo
    initMessageListener();
})();
