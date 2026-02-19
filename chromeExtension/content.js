/**
 * Content Script - Multi-platform overlay for MedLog
 *
 * Supports Google Meet and Zoom Web Client.
 * Injects a non-intrusive floating badge on meeting pages.
 * Badge click opens the full panel (on-demand, not auto-inject).
 *
 * Session state machine: pre -> recording -> post
 * Post-session: cards become editable textareas + export bar.
 */
(function () {
    'use strict';

    // Prevent double-injection (keyed on badge, not panel)
    if (document.getElementById('drt-badge')) return;

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

    // Check current URL
    if (!isMeetingUrl(window.location.pathname, window.location.hostname)) {
        // Watch for SPA navigation
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
        return;
    }

    injectBadge();

    // ─── State ─────────────────────────────────────────────────

    let sessionPhase = 'pre'; // 'pre' | 'recording' | 'post'
    let isCollapsed = false;
    let isPaused = false;
    let currentPatient = { name: '', age: '', gender: '' };
    let latestExtraction = {};
    let appointmentData = null;      // Store received appointment/patient data (via postMessage)

    // ─── Mic Capture State ──────────────────────────────────────

    let micStream = null;
    let micAudioContext = null;
    let micScriptProcessor = null;
    let micBuffer = [];
    let micChunkTimer = null;
    let micTargetSampleRate = 16000;
    let micChunkDuration = 7; // seconds (overridden by server config)

    /**
     * Downsample audio from native rate to target rate using linear interpolation
     */
    function downsampleMic(samples, fromRate, toRate) {
        if (fromRate === toRate) return samples;

        const ratio = fromRate / toRate;
        const newLength = Math.round(samples.length / ratio);
        const result = new Float32Array(newLength);

        for (let i = 0; i < newLength; i++) {
            const srcIndex = i * ratio;
            const floor = Math.floor(srcIndex);
            const ceil = Math.min(floor + 1, samples.length - 1);
            const frac = srcIndex - floor;
            result[i] = samples[floor] * (1 - frac) + samples[ceil] * frac;
        }

        return result;
    }

    /**
     * Flush accumulated mic buffer: downsample, WAV encode, send to background
     */
    function flushMicBuffer() {
        if (micBuffer.length === 0 || !micAudioContext) return;

        // Concatenate accumulated samples
        let totalLength = 0;
        for (const chunk of micBuffer) totalLength += chunk.length;
        const allSamples = new Float32Array(totalLength);
        let offset = 0;
        for (const chunk of micBuffer) {
            allSamples.set(chunk, offset);
            offset += chunk.length;
        }
        micBuffer = [];

        // Downsample from native rate to 16kHz
        const nativeRate = micAudioContext.sampleRate;
        const downsampled = downsampleMic(allSamples, nativeRate, micTargetSampleRate);

        // Encode to WAV
        const wavBlob = WavEncoder.encode(downsampled, micTargetSampleRate, 1);

        // Convert Blob to base64 and send to background
        const reader = new FileReader();
        reader.onloadend = () => {
            const base64Data = reader.result.split(',')[1];
            chrome.runtime.sendMessage({
                type: 'audio-chunk',
                audio_data: base64Data
            });
            console.log(`[drT Content] Sent mic chunk: ${allSamples.length} native -> ${downsampled.length} @${micTargetSampleRate}Hz`);
        };
        reader.onerror = (err) => {
            console.error('[drT Content] FileReader error:', err);
        };
        reader.readAsDataURL(wavBlob);
    }

    /**
     * Start capturing microphone audio via getUserMedia
     * Works because content script runs in the page context (meet.google.com)
     * where mic permission is already granted for the video call.
     */
    async function startMicCapture() {
        try {
            micStream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true
                }
            });
            console.log('[drT Content] Mic stream acquired');

            // Create AudioContext at native sample rate (do NOT force 16kHz)
            micAudioContext = new AudioContext();
            const nativeRate = micAudioContext.sampleRate;
            console.log(`[drT Content] Mic AudioContext at ${nativeRate}Hz, target: ${micTargetSampleRate}Hz`);

            const source = micAudioContext.createMediaStreamSource(micStream);

            // ScriptProcessorNode to accumulate raw samples
            micScriptProcessor = micAudioContext.createScriptProcessor(4096, 1, 1);
            micScriptProcessor.onaudioprocess = (event) => {
                const inputData = event.inputBuffer.getChannelData(0);
                micBuffer.push(new Float32Array(inputData));
            };

            source.connect(micScriptProcessor);
            // ScriptProcessor must connect to destination to keep firing
            micScriptProcessor.connect(micAudioContext.destination);

            // Flush buffer every chunkDuration seconds
            micChunkTimer = setInterval(flushMicBuffer, micChunkDuration * 1000);

            console.log('[drT Content] Mic capture started');
        } catch (err) {
            console.warn('[drT Content] Mic capture failed:', err.message);
            // Non-fatal: tab audio still works via offscreen
        }
    }

    /**
     * Stop mic capture and clean up all resources
     */
    function stopMicCapture() {
        if (micChunkTimer) {
            clearInterval(micChunkTimer);
            micChunkTimer = null;
        }

        // Flush any remaining samples
        flushMicBuffer();

        if (micScriptProcessor) {
            micScriptProcessor.disconnect();
            micScriptProcessor = null;
        }

        if (micStream) {
            micStream.getTracks().forEach(track => track.stop());
            micStream = null;
        }

        if (micAudioContext) {
            micAudioContext.close().catch(() => {});
            micAudioContext = null;
        }

        micBuffer = [];
        console.log('[drT Content] Mic capture stopped');
    }

    // ─── Badge ─────────────────────────────────────────────────

    function injectBadge() {
        const badge = document.createElement('div');
        badge.id = 'drt-badge';
        badge.className = 'drt-badge drt-badge-detected';

        // Use MedLog logo image
        const logoImg = document.createElement('img');
        logoImg.src = chrome.runtime.getURL('icons/logo.png');
        logoImg.alt = 'MedLog';
        logoImg.className = 'drt-badge-logo';
        badge.appendChild(logoImg);

        badge.title = 'MedLog - Click to open';
        badge.addEventListener('click', async () => {
            const panel = document.getElementById('drt-panel');
            if (panel) {
                // Panel already exists, just toggle visibility
                panel.style.display = panel.style.display === 'none' ? 'flex' : 'none';
            } else {
                // First time opening - request patient data from EMR
                await requestPatientDataFromEMR();
                injectPanel();
            }
        });
        document.body.appendChild(badge);
    }

    // ─── Panel ─────────────────────────────────────────────────

    function injectPanel() {
        if (document.getElementById('drt-panel')) return;

        const panel = document.createElement('div');
        panel.id = 'drt-panel';
        panel.className = 'drt-panel';
        panel.innerHTML = `
            <div class="drt-header" id="drt-header">
                <div class="drt-brand">
                    <div class="drt-logo-icon">M</div>
                    <span class="drt-logo">MedLog</span>
                    <span class="drt-status" id="drt-status">Ready</span>
                </div>
                <div class="drt-controls">
                    <button class="drt-btn-icon" id="drt-collapse" title="Collapse">&#x2015;</button>
                    <button class="drt-btn-icon" id="drt-close" title="Close">&#x2715;</button>
                </div>
            </div>

            <div class="drt-body" id="drt-body">
                <!-- Compact patient display (shown when appointmentData exists) -->
                <div id="drt-patient-display" class="drt-patient-display" style="display: none;">
                    <div class="drt-patient-avatar" id="drt-patient-avatar">PK</div>
                    <div class="drt-patient-details">
                        <div class="drt-patient-name" id="drt-patient-name-display">Patient Name</div>
                        <div class="drt-patient-meta">
                            <span class="drt-patient-tag" id="drt-patient-age-tag"></span>
                            <span class="drt-patient-tag" id="drt-patient-gender-tag"></span>
                            <span class="drt-patient-tag" id="drt-patient-id-tag"></span>
                        </div>
                    </div>
                </div>

                <!-- Full patient form (shown when no appointmentData) -->
                <div id="drt-patient-form-section">
                    <div class="drt-section-title">Patient Info</div>
                    <div class="drt-form-row">
                        <input type="text" id="drt-patient-name" class="drt-input" placeholder="Patient Name" />
                    </div>
                    <div class="drt-form-row drt-form-row-split">
                        <input type="number" id="drt-patient-age" class="drt-input drt-input-small" placeholder="Age" min="0" max="150" />
                        <select id="drt-patient-gender" class="drt-input">
                            <option value="" disabled selected>Gender</option>
                            <option value="Male">Male</option>
                            <option value="Female">Female</option>
                            <option value="Other">Other</option>
                        </select>
                    </div>
                </div>

                <!-- Session controls -->
                <div class="drt-session-controls" id="drt-session-actions">
                    <button id="drt-start-btn" class="drt-btn drt-btn-start">&#x25B6; Start Session</button>
                    <button id="drt-pause-btn" class="drt-btn drt-btn-pause" style="display: none;">Pause</button>
                    <button id="drt-stop-btn" class="drt-btn drt-btn-stop" disabled>&#x25A0; End Session</button>
                </div>

                <div class="drt-results" id="drt-results">
                    <div class="drt-card drt-card-chief">
                        <div class="drt-card-header">
                            <span class="drt-card-icon">&#x1FA7A;</span>
                            <span class="drt-card-title">Chief Complaint</span>
                            <span class="drt-card-badge" id="drt-badge-chief-complaint">PENDING</span>
                        </div>
                        <div class="drt-card-content drt-empty" id="drt-chief-complaint">Waiting for session to begin...</div>
                    </div>
                    <div class="drt-card drt-card-diagnosis">
                        <div class="drt-card-header">
                            <span class="drt-card-icon">&#x1F4CB;</span>
                            <span class="drt-card-title">Diagnosis</span>
                            <span class="drt-card-badge" id="drt-badge-diagnosis">PENDING</span>
                        </div>
                        <div class="drt-card-content drt-empty" id="drt-diagnosis">Waiting for session to begin...</div>
                    </div>
                    <div class="drt-card drt-card-medicine">
                        <div class="drt-card-header">
                            <span class="drt-card-icon">&#x1F48A;</span>
                            <span class="drt-card-title">Medicine</span>
                            <span class="drt-card-badge" id="drt-badge-medicine">PENDING</span>
                        </div>
                        <div class="drt-card-content drt-empty" id="drt-medicine">Waiting for session to begin...</div>
                    </div>
                    <div class="drt-card drt-card-advice">
                        <div class="drt-card-header">
                            <span class="drt-card-icon">&#x1F4AC;</span>
                            <span class="drt-card-title">Advice</span>
                            <span class="drt-card-badge" id="drt-badge-advice">PENDING</span>
                        </div>
                        <div class="drt-card-content drt-empty" id="drt-advice">Waiting for session to begin...</div>
                    </div>
                    <div class="drt-card drt-card-nextsteps">
                        <div class="drt-card-header">
                            <span class="drt-card-icon">&#x27A1;</span>
                            <span class="drt-card-title">Next Steps</span>
                            <span class="drt-card-badge" id="drt-badge-next-steps">PENDING</span>
                        </div>
                        <div class="drt-card-content drt-empty" id="drt-next-steps">Waiting for session to begin...</div>
                    </div>
                </div>
            </div>

            <div class="drt-footer">
                <span class="drt-footer-version">MedLog v2.1 &middot; HIPAA Compliant</span>
                <span class="drt-footer-status" id="drt-footer-status">&#x25CF; Not Recording</span>
            </div>
        `;

        document.body.appendChild(panel);
        setupPanelBehavior();
        updatePatientDisplay();
    }

    /**
     * Update patient display based on appointmentData availability
     * Shows compact display if appointmentData exists, otherwise shows full form
     */
    function updatePatientDisplay() {
        const displayEl = document.getElementById('drt-patient-display');
        const formEl = document.getElementById('drt-patient-form-section');

        if (!displayEl || !formEl) return;

        if (appointmentData && appointmentData.patient) {
            // Show compact display with avatar and metadata pills
            displayEl.style.display = 'flex';
            formEl.style.display = 'none';

            const { name, age, gender } = appointmentData.patient;
            const appointmentId = appointmentData.appointmentId || '';

            // Avatar initials
            const avatarEl = document.getElementById('drt-patient-avatar');
            if (avatarEl) {
                const initials = name.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2);
                avatarEl.textContent = initials;
            }

            const nameEl = document.getElementById('drt-patient-name-display');
            if (nameEl) nameEl.textContent = name;

            const ageTag = document.getElementById('drt-patient-age-tag');
            if (ageTag) ageTag.textContent = age ? `${age} yrs` : '';

            const genderTag = document.getElementById('drt-patient-gender-tag');
            if (genderTag) genderTag.textContent = gender || '';

            const idTag = document.getElementById('drt-patient-id-tag');
            if (idTag) idTag.textContent = appointmentId ? `ID #${appointmentId}` : '';
        } else {
            // Show full form for manual entry
            displayEl.style.display = 'none';
            formEl.style.display = 'block';
        }
    }

    function setupPanelBehavior() {
        const panel = document.getElementById('drt-panel');
        const header = document.getElementById('drt-header');
        const body = document.getElementById('drt-body');
        const collapseBtn = document.getElementById('drt-collapse');
        const closeBtn = document.getElementById('drt-close');
        const startBtn = document.getElementById('drt-start-btn');
        const pauseBtn = document.getElementById('drt-pause-btn');
        const stopBtn = document.getElementById('drt-stop-btn');

        // ─── Dragging ──────────────────────────────────────
        let isDragging = false;
        let dragOffsetX = 0;
        let dragOffsetY = 0;

        header.addEventListener('mousedown', (e) => {
            if (e.target.closest('.drt-btn-icon')) return;
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

        // ─── Collapse / Close ──────────────────────────────
        collapseBtn.addEventListener('click', () => {
            isCollapsed = !isCollapsed;
            body.style.display = isCollapsed ? 'none' : '';
            collapseBtn.innerHTML = isCollapsed ? '&#x2B1C;' : '&#x2015;';
            collapseBtn.title = isCollapsed ? 'Expand' : 'Collapse';
        });

        closeBtn.addEventListener('click', () => {
            if (sessionPhase === 'recording') {
                if (!confirm('Session is active. Stop session and close panel?')) return;
                doStopSession();
            }
            panel.style.display = 'none';
        });

        // ─── Start Session ─────────────────────────────────
        startBtn.addEventListener('click', () => {
            let name, age, gender;
            let appointmentId = null;
            let history = null;

            // Use appointmentData if available, otherwise validate manual form
            if (appointmentData && appointmentData.patient) {
                // EMR mode: use received appointment data
                name = appointmentData.patient.name;
                age = appointmentData.patient.age || 0;
                gender = appointmentData.patient.gender || '';
                appointmentId = appointmentData.appointmentId || null;
                history = appointmentData.patient.history || null;
            } else {
                // Manual mode: validate form inputs
                const nameInput = document.getElementById('drt-patient-name');
                const ageInput = document.getElementById('drt-patient-age');
                const genderInput = document.getElementById('drt-patient-gender');

                name = nameInput.value.trim();
                age = parseInt(ageInput.value);
                gender = genderInput.value;

                if (!name) { nameInput.focus(); return alert('Please enter patient name'); }
                if (!age || age < 0 || age > 150) { ageInput.focus(); return alert('Please enter a valid age'); }
                if (!gender) { genderInput.focus(); return alert('Please select gender'); }
            }

            currentPatient = { name, age, gender };
            setStatus('Connecting...', 'connecting');

            // Build message payload
            const payload = {
                type: 'start-session',
                patient: { name, age, gender }
            };

            // Include appointmentId and history if available
            if (appointmentId) payload.appointmentId = appointmentId;
            if (history) payload.history = history;

            chrome.runtime.sendMessage(payload, (response) => {
                if (chrome.runtime.lastError) {
                    setStatus('Error', 'error');
                    alert('Extension error: ' + chrome.runtime.lastError.message);
                    return;
                }
                if (response && response.ok) {
                    // session-started message will update UI
                } else {
                    setStatus('Failed', 'error');
                    alert('Failed to start: ' + (response ? response.error : 'Unknown error'));
                }
            });
        });

        // ─── Pause / Resume ────────────────────────────────
        pauseBtn.addEventListener('click', () => {
            if (isPaused) {
                // Resume
                isPaused = false;
                pauseBtn.textContent = 'Pause';
                setStatus('Recording', 'recording');
                startMicCapture();
            } else {
                // Pause
                isPaused = true;
                pauseBtn.textContent = 'Resume';
                setStatus('Paused', '');
                stopMicCapture();
            }
        });

        // ─── Stop Session ──────────────────────────────────
        stopBtn.addEventListener('click', () => {
            doStopSession();
        });
    }

    function doStopSession() {
        stopMicCapture();
        chrome.runtime.sendMessage({ type: 'stop-session' }, () => {
            // session-ended message will update UI
        });
    }

    // ─── UI Helpers ────────────────────────────────────────────

    function setStatus(text, state) {
        const statusEl = document.getElementById('drt-status');
        if (statusEl) {
            statusEl.textContent = text;
            statusEl.className = 'drt-status';
            if (state) statusEl.classList.add('drt-status-' + state);
        }
        // Update footer status
        const footerStatus = document.getElementById('drt-footer-status');
        if (footerStatus) {
            if (state === 'recording') {
                footerStatus.textContent = '\u25CF Recording';
                footerStatus.className = 'drt-footer-status drt-footer-recording';
            } else {
                footerStatus.textContent = '\u25CF Not Recording';
                footerStatus.className = 'drt-footer-status';
            }
        }
    }

    function setSessionActive(active) {
        const startBtn = document.getElementById('drt-start-btn');
        const pauseBtn = document.getElementById('drt-pause-btn');
        const stopBtn = document.getElementById('drt-stop-btn');
        const nameInput = document.getElementById('drt-patient-name');
        const ageInput = document.getElementById('drt-patient-age');
        const genderInput = document.getElementById('drt-patient-gender');

        if (startBtn) {
            startBtn.disabled = active;
            startBtn.style.display = active ? 'none' : '';
        }
        if (pauseBtn) {
            pauseBtn.style.display = active ? '' : 'none';
            pauseBtn.disabled = false;
        }
        if (stopBtn) stopBtn.disabled = !active;
        if (nameInput) nameInput.disabled = active;
        if (ageInput) ageInput.disabled = active;
        if (genderInput) genderInput.disabled = active;

        // Update badge state
        const badge = document.getElementById('drt-badge');
        if (badge) {
            badge.classList.toggle('drt-badge-active', active);
            badge.classList.toggle('drt-badge-detected', !active);
        }
    }

    function updateExtractionResults(extraction) {
        latestExtraction = extraction;
        const fields = {
            chief_complaint: document.getElementById('drt-chief-complaint'),
            diagnosis: document.getElementById('drt-diagnosis'),
            medicine: document.getElementById('drt-medicine'),
            advice: document.getElementById('drt-advice'),
            next_steps: document.getElementById('drt-next-steps')
        };

        for (const [key, el] of Object.entries(fields)) {
            if (!el) continue;
            const value = extraction[key];
            if (value && value.trim()) {
                el.textContent = value;
                el.classList.remove('drt-empty');
                // Update card badge
                const badgeId = 'drt-badge-' + key.replace(/_/g, '-');
                const badge = document.getElementById(badgeId);
                if (badge) {
                    badge.textContent = 'UPDATED';
                    badge.classList.add('drt-badge-updated');
                }
            }
        }
    }

    function resetResults() {
        const ids = ['drt-chief-complaint', 'drt-diagnosis', 'drt-medicine', 'drt-advice', 'drt-next-steps'];
        const badgeIds = ['drt-badge-chief-complaint', 'drt-badge-diagnosis', 'drt-badge-medicine', 'drt-badge-advice', 'drt-badge-next-steps'];
        for (const id of ids) {
            const el = document.getElementById(id);
            if (el) {
                el.textContent = 'Waiting for session to begin...';
                el.classList.add('drt-empty');
            }
        }
        for (const id of badgeIds) {
            const el = document.getElementById(id);
            if (el) {
                el.textContent = 'PENDING';
                el.classList.remove('drt-badge-updated');
            }
        }
    }

    // ─── Post-Session Transition ───────────────────────────────

    function transitionToPostSession() {
        sessionPhase = 'post';
        setStatus('Session Complete', '');

        const fieldKeys = ['chief_complaint', 'diagnosis', 'medicine', 'advice', 'next_steps'];
        const fieldIds = {
            chief_complaint: 'drt-chief-complaint',
            diagnosis: 'drt-diagnosis',
            medicine: 'drt-medicine',
            advice: 'drt-advice',
            next_steps: 'drt-next-steps'
        };

        // Replace card content divs with editable textareas
        for (const key of fieldKeys) {
            const contentEl = document.getElementById(fieldIds[key]);
            if (!contentEl) continue;

            const currentText = contentEl.classList.contains('drt-empty') ? '' : contentEl.textContent;
            const textarea = document.createElement('textarea');
            textarea.id = 'drt-edit-' + key;
            textarea.className = 'drt-card-textarea';
            textarea.value = currentText;
            textarea.placeholder = 'No data captured';
            textarea.rows = 3;

            contentEl.parentNode.replaceChild(textarea, contentEl);
        }

        // Hide start/stop buttons
        const sessionActions = document.getElementById('drt-session-actions');
        if (sessionActions) sessionActions.style.display = 'none';

        // Inject export bar
        const results = document.getElementById('drt-results');
        if (results) {
            const exportBar = document.createElement('div');
            exportBar.id = 'drt-export-bar';
            exportBar.className = 'drt-export-bar';
            exportBar.innerHTML = `
                <div class="drt-section-title">Export</div>
                <div class="drt-export-actions">
                    <button class="drt-btn-export drt-btn-export-primary" id="drt-export-emr" style="grid-column: 1 / -1;">Export to EMR</button>
                    <button class="drt-btn-export" id="drt-export-pdf">Export PDF</button>
                    <button class="drt-btn-export" id="drt-export-email">Open in Gmail</button>
                    <button class="drt-btn-export" id="drt-export-clipboard">Copy to Clipboard</button>
                    <button class="drt-btn-export" id="drt-export-txt">Download TXT</button>
                </div>
                <button class="drt-btn-new-session" id="drt-new-session">+ New Session</button>
            `;
            results.parentNode.insertBefore(exportBar, results.nextSibling);

            // Wire export buttons

            // Export to EMR
            document.getElementById('drt-export-emr').addEventListener('click', () => {
                const extraction = {
                    chief_complaint: document.getElementById('drt-edit-chief_complaint')?.value || '',
                    diagnosis: document.getElementById('drt-edit-diagnosis')?.value || '',
                    medicine: document.getElementById('drt-edit-medicine')?.value || '',
                    advice: document.getElementById('drt-edit-advice')?.value || '',
                    next_steps: document.getElementById('drt-edit-next_steps')?.value || ''
                };

                const success = exportToEMR(extraction);
                if (success) {
                    showToast('Results sent to EMR page!');
                } else {
                    showToast('EMR page not available. Please open the EMR page first.');
                }
            });

            document.getElementById('drt-export-pdf').addEventListener('click', async () => {
                const settings = await chrome.storage.local.get(['doctorName', 'clinicName']);
                window.DrTExport.exportPDF(currentPatient, {
                    doctorName: settings.doctorName || '',
                    clinicName: settings.clinicName || ''
                });
            });

            document.getElementById('drt-export-email').addEventListener('click', () => {
                window.DrTExport.exportEmail(currentPatient);
                showToast('Content also copied to clipboard');
            });

            document.getElementById('drt-export-clipboard').addEventListener('click', () => {
                const ok = window.DrTExport.exportClipboard(currentPatient);
                showToast(ok !== false ? 'Copied to clipboard!' : 'Copy failed');
            });

            document.getElementById('drt-export-txt').addEventListener('click', () => {
                window.DrTExport.exportTXT(currentPatient);
            });

            document.getElementById('drt-new-session').addEventListener('click', () => {
                transitionToPreSession();
            });
        }
    }

    function transitionToPreSession() {
        sessionPhase = 'pre';
        latestExtraction = {};
        setStatus('Ready', '');

        const fieldKeys = ['chief_complaint', 'diagnosis', 'medicine', 'advice', 'next_steps'];
        const fieldIds = {
            chief_complaint: 'drt-chief-complaint',
            diagnosis: 'drt-diagnosis',
            medicine: 'drt-medicine',
            advice: 'drt-advice',
            next_steps: 'drt-next-steps'
        };

        // Replace textareas back with content divs
        for (const key of fieldKeys) {
            const textarea = document.getElementById('drt-edit-' + key);
            if (!textarea) continue;

            const div = document.createElement('div');
            div.id = fieldIds[key];
            div.className = 'drt-card-content drt-empty';
            div.textContent = 'Waiting for session to begin...';

            textarea.parentNode.replaceChild(div, textarea);

            // Reset badge
            const badgeId = 'drt-badge-' + key.replace(/_/g, '-');
            const badge = document.getElementById(badgeId);
            if (badge) {
                badge.textContent = 'PENDING';
                badge.classList.remove('drt-badge-updated');
            }
        }

        // Remove export bar
        const exportBar = document.getElementById('drt-export-bar');
        if (exportBar) exportBar.remove();

        // Show start/stop buttons
        const sessionActions = document.getElementById('drt-session-actions');
        if (sessionActions) sessionActions.style.display = '';

        // Reset form
        const nameInput = document.getElementById('drt-patient-name');
        const ageInput = document.getElementById('drt-patient-age');
        const genderInput = document.getElementById('drt-patient-gender');
        if (nameInput) { nameInput.value = ''; nameInput.disabled = false; }
        if (ageInput) { ageInput.value = ''; ageInput.disabled = false; }
        if (genderInput) { genderInput.value = ''; genderInput.disabled = false; }

        const startBtn = document.getElementById('drt-start-btn');
        const stopBtn = document.getElementById('drt-stop-btn');
        if (startBtn) startBtn.disabled = false;
        if (stopBtn) stopBtn.disabled = true;

        // Reset badge
        const badge = document.getElementById('drt-badge');
        if (badge) {
            badge.classList.remove('drt-badge-active');
            badge.classList.add('drt-badge-detected');
        }
    }

    // ─── Toast Notification ────────────────────────────────────

    function showToast(message) {
        // Remove existing toast
        const existing = document.getElementById('drt-toast');
        if (existing) existing.remove();

        const toast = document.createElement('div');
        toast.id = 'drt-toast';
        toast.className = 'drt-toast';
        toast.textContent = message;
        document.body.appendChild(toast);

        // Trigger animation
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
                sessionPhase = 'recording';
                isPaused = false;
                setSessionActive(true);
                setStatus('Recording', 'recording');
                resetResults();
                // Apply server audio config if provided
                if (message.audioConfig) {
                    micTargetSampleRate = message.audioConfig.sample_rate || 16000;
                    micChunkDuration = message.audioConfig.chunk_duration_seconds || 7;
                }
                startMicCapture();
                break;

            case 'session-ended':
                stopMicCapture();
                setSessionActive(false);
                if (sessionPhase === 'recording') {
                    transitionToPostSession();
                }
                if (message.reason) {
                    console.warn('[drT] Session ended:', message.reason);
                }
                break;

            case 'extraction_update':
                updateExtractionResults(message.extraction);
                break;

            case 'error':
                console.error('[drT] Error from backend:', message.message);
                setStatus('Error', 'error');
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

        // Store appointment data for use in session and export
        appointmentData = data;

        // Update panel display if panel already exists
        const panel = document.getElementById('drt-panel');
        if (panel) {
            updatePatientDisplay();
        }
        // If panel doesn't exist yet, updatePatientDisplay will be called by injectPanel
    }

    /**
     * Export extraction results back to EMR page via Broadcast Channel
     * Called after session ends and user clicks export
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
