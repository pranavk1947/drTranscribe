/**
 * Content Script - Multi-platform overlay for drTranscribe
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
    let currentPatient = { name: '', age: '', gender: '' };
    let latestExtraction = {};

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
        badge.textContent = 'drT';
        badge.title = 'drTranscribe - Click to open';
        badge.addEventListener('click', () => {
            const panel = document.getElementById('drt-panel');
            if (panel) {
                panel.style.display = panel.style.display === 'none' ? 'flex' : 'none';
            } else {
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
                    <span class="drt-logo">drT</span>
                    <span class="drt-status" id="drt-status">Ready</span>
                </div>
                <div class="drt-controls">
                    <button class="drt-btn-icon" id="drt-collapse" title="Collapse">&#x2015;</button>
                    <button class="drt-btn-icon" id="drt-close" title="Close">&#x2715;</button>
                </div>
            </div>

            <div class="drt-body" id="drt-body">
                <div class="drt-section drt-patient-form">
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
                    <div class="drt-form-row drt-form-actions" id="drt-session-actions">
                        <button id="drt-start-btn" class="drt-btn drt-btn-start">Start Session</button>
                        <button id="drt-stop-btn" class="drt-btn drt-btn-stop" disabled>Stop</button>
                    </div>
                </div>

                <div class="drt-section drt-results" id="drt-results">
                    <div class="drt-card">
                        <div class="drt-card-title">Chief Complaint</div>
                        <div class="drt-card-content drt-empty" id="drt-chief-complaint">Waiting for session...</div>
                    </div>
                    <div class="drt-card">
                        <div class="drt-card-title">Diagnosis</div>
                        <div class="drt-card-content drt-empty" id="drt-diagnosis">Waiting for session...</div>
                    </div>
                    <div class="drt-card">
                        <div class="drt-card-title">Medicine</div>
                        <div class="drt-card-content drt-empty" id="drt-medicine">Waiting for session...</div>
                    </div>
                    <div class="drt-card">
                        <div class="drt-card-title">Advice</div>
                        <div class="drt-card-content drt-empty" id="drt-advice">Waiting for session...</div>
                    </div>
                    <div class="drt-card">
                        <div class="drt-card-title">Next Steps</div>
                        <div class="drt-card-content drt-empty" id="drt-next-steps">Waiting for session...</div>
                    </div>
                </div>
            </div>
        `;

        document.body.appendChild(panel);
        setupPanelBehavior();
    }

    function setupPanelBehavior() {
        const panel = document.getElementById('drt-panel');
        const header = document.getElementById('drt-header');
        const body = document.getElementById('drt-body');
        const collapseBtn = document.getElementById('drt-collapse');
        const closeBtn = document.getElementById('drt-close');
        const startBtn = document.getElementById('drt-start-btn');
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
            const nameInput = document.getElementById('drt-patient-name');
            const ageInput = document.getElementById('drt-patient-age');
            const genderInput = document.getElementById('drt-patient-gender');

            const name = nameInput.value.trim();
            const age = parseInt(ageInput.value);
            const gender = genderInput.value;

            if (!name) { nameInput.focus(); return alert('Please enter patient name'); }
            if (!age || age < 0 || age > 150) { ageInput.focus(); return alert('Please enter a valid age'); }
            if (!gender) { genderInput.focus(); return alert('Please select gender'); }

            currentPatient = { name, age, gender };
            setStatus('Connecting...', 'connecting');

            chrome.runtime.sendMessage({
                type: 'start-session',
                patient: { name, age, gender }
            }, (response) => {
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
        if (!statusEl) return;
        statusEl.textContent = text;
        statusEl.className = 'drt-status';
        if (state) statusEl.classList.add('drt-status-' + state);
    }

    function setSessionActive(active) {
        const startBtn = document.getElementById('drt-start-btn');
        const stopBtn = document.getElementById('drt-stop-btn');
        const nameInput = document.getElementById('drt-patient-name');
        const ageInput = document.getElementById('drt-patient-age');
        const genderInput = document.getElementById('drt-patient-gender');

        if (startBtn) startBtn.disabled = active;
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
            }
        }
    }

    function resetResults() {
        const ids = ['drt-chief-complaint', 'drt-diagnosis', 'drt-medicine', 'drt-advice', 'drt-next-steps'];
        for (const id of ids) {
            const el = document.getElementById(id);
            if (el) {
                el.textContent = 'Waiting for session...';
                el.classList.add('drt-empty');
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
                    <button class="drt-btn-export drt-btn-export-primary" id="drt-export-pdf">Export PDF</button>
                    <button class="drt-btn-export" id="drt-export-email">Open in Gmail</button>
                    <button class="drt-btn-export" id="drt-export-clipboard">Copy to Clipboard</button>
                    <button class="drt-btn-export" id="drt-export-txt">Download TXT</button>
                </div>
                <button class="drt-btn-new-session" id="drt-new-session">+ New Session</button>
            `;
            results.parentNode.insertBefore(exportBar, results.nextSibling);

            // Wire export buttons
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
            div.textContent = 'Waiting for session...';

            textarea.parentNode.replaceChild(div, textarea);
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
})();
