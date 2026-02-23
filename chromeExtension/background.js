/**
 * Background Service Worker - Orchestration hub for drTranscribe extension
 *
 * Responsibilities:
 * 1. Manage chrome.tabCapture to get streamId for the Meet tab
 * 2. Create/manage offscreen document lifecycle
 * 3. Manage WebSocket connection to backend
 * 4. Relay audio chunks from offscreen -> WebSocket -> backend
 * 5. Relay extraction updates from backend -> content script
 * 6. Store/load server URL from chrome.storage.local
 */

const DEFAULT_SERVER_URL = 'http://localhost:8000';

let websocket = null;
let activeTabId = null;
let isSessionActive = false;
let hasOffscreenDocument = false;

// ─── Server URL Management ───────────────────────────────────────────

async function getServerUrl() {
    try {
        const result = await chrome.storage.local.get('serverUrl');
        return result.serverUrl || DEFAULT_SERVER_URL;
    } catch {
        return DEFAULT_SERVER_URL;
    }
}

// ─── Audio Config ────────────────────────────────────────────────────

async function fetchAudioConfig(serverUrl) {
    try {
        const response = await fetch(`${serverUrl}/api/config`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const config = await response.json();
        console.log('[BG] Fetched audio config:', config);
        return config.audio || { chunk_duration_seconds: 7, sample_rate: 16000, channels: 1 };
    } catch (err) {
        console.warn('[BG] Failed to fetch audio config, using defaults:', err.message);
        return { chunk_duration_seconds: 7, sample_rate: 16000, channels: 1 };
    }
}

// ─── Offscreen Document Management ──────────────────────────────────

async function ensureOffscreenDocument() {
    if (hasOffscreenDocument) return;

    try {
        // Check if one already exists
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
            justification: 'Capture tab audio for medical transcription'
        });
        hasOffscreenDocument = true;
        console.log('[BG] Offscreen document created');
    } catch (err) {
        console.error('[BG] Failed to create offscreen document:', err);
        throw err;
    }
}

async function closeOffscreenDocument() {
    if (!hasOffscreenDocument) return;
    try {
        await chrome.offscreen.closeDocument();
    } catch {
        // Already closed
    }
    hasOffscreenDocument = false;
    console.log('[BG] Offscreen document closed');
}

// ─── WebSocket Management ───────────────────────────────────────────

async function connectWebSocket(serverUrl, patientInfo) {
    return new Promise((resolve, reject) => {
        if (!patientInfo?.name || !patientInfo?.age || !patientInfo?.gender) {
            reject(new Error('Invalid patient information'));
            return;
        }

        const wsProtocol = serverUrl.startsWith('https') ? 'wss' : 'ws';
        const wsHost = serverUrl.replace(/^https?:\/\//, '');
        const wsUrl = `${wsProtocol}://${wsHost}/ws`;

        console.log('[BG] Connecting WebSocket to:', wsUrl);
        websocket = new WebSocket(wsUrl);

        websocket.onopen = () => {
            console.log('[BG] WebSocket connected');

            // Send start_session message
            const startMessage = {
                type: 'start_session',
                patient: patientInfo
            };
            websocket.send(JSON.stringify(startMessage));
            console.log('[BG] Sent start_session:', patientInfo);
            resolve();
        };

        websocket.onmessage = (event) => {
            try {
                const message = JSON.parse(event.data);
                console.log('[BG] Received from backend:', message.type);

                // Forward extraction updates and errors to content script
                if (activeTabId && (message.type === 'extraction_update' || message.type === 'error')) {
                    chrome.tabs.sendMessage(activeTabId, message).catch(err => {
                        console.warn('[BG] Failed to send to content script:', err.message);
                    });
                }
            } catch (err) {
                console.error('[BG] Failed to parse WebSocket message:', err);
            }
        };

        websocket.onerror = (event) => {
            console.error('[BG] WebSocket error:', event);
            reject(new Error('WebSocket connection failed'));
        };

        websocket.onclose = () => {
            console.log('[BG] WebSocket closed');
            websocket = null;
            if (isSessionActive) {
                // Unexpected close - notify content script
                if (activeTabId) {
                    chrome.tabs.sendMessage(activeTabId, {
                        type: 'session-ended',
                        reason: 'WebSocket disconnected'
                    }).catch(() => {});
                }
                isSessionActive = false;
            }
        };
    });
}

function disconnectWebSocket() {
    return new Promise((resolve) => {
        if (!websocket) {
            resolve();
            return;
        }

        if (websocket.readyState !== WebSocket.OPEN) {
            websocket.close();
            websocket = null;
            resolve();
            return;
        }

        // Wait for server acknowledgment before closing
        const ws = websocket;
        let resolved = false;

        const cleanup = () => {
            if (resolved) return;
            resolved = true;
            try { ws.close(); } catch {}
            websocket = null;
            resolve();
        };

        // Listen for session_stopped acknowledgment from server
        const originalOnMessage = ws.onmessage;
        ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                if (msg.type === 'session_stopped') {
                    console.log('[BG] Server acknowledged session stop');
                    cleanup();
                    return;
                }
                // Forward other messages (extraction updates) as usual
                if (originalOnMessage) originalOnMessage(event);
            } catch {
                if (originalOnMessage) originalOnMessage(event);
            }
        };

        // Safety timeout — close after 5s even if no ack
        setTimeout(() => {
            if (!resolved) {
                console.warn('[BG] Timed out waiting for server ack, closing WebSocket');
                cleanup();
            }
        }, 5000);

        // Send stop_session
        ws.send(JSON.stringify({ type: 'stop_session' }));
        console.log('[BG] Sent stop_session, waiting for server ack...');
    });
}

function sendAudioChunk(audioData, source) {
    if (websocket && websocket.readyState === WebSocket.OPEN) {
        const message = {
            type: 'audio_chunk',
            audio_data: audioData,
            source: source || 'unknown'
        };
        websocket.send(JSON.stringify(message));
    }
}

// ─── Session Management ─────────────────────────────────────────────

async function startSession(tabId, patientInfo) {
    try {
        activeTabId = tabId;

        // 1. Get server URL and audio config
        const serverUrl = await getServerUrl();
        const audioConfig = await fetchAudioConfig(serverUrl);

        // 2. Connect WebSocket
        await connectWebSocket(serverUrl, patientInfo);

        // 3. Get tab capture stream ID
        const streamId = await chrome.tabCapture.getMediaStreamId({
            targetTabId: tabId
        });
        console.log('[BG] Got tabCapture streamId');

        // 4. Ensure offscreen document exists
        await ensureOffscreenDocument();

        // 5. Tell offscreen to start capturing
        await chrome.runtime.sendMessage({
            type: 'start-capture',
            streamId: streamId,
            audioConfig: audioConfig
        });

        isSessionActive = true;
        console.log('[BG] Session started for tab:', tabId);

        // Notify content script (include audio config for mic capture)
        chrome.tabs.sendMessage(tabId, {
            type: 'session-started',
            audioConfig: audioConfig
        }).catch(() => {});

    } catch (err) {
        console.error('[BG] Failed to start session:', err);
        // Clean up on failure
        disconnectWebSocket();
        activeTabId = null;
        isSessionActive = false;
        throw err;
    }
}

async function stopSession() {
    console.log('[BG] Stopping session');

    // 1. Tell offscreen to stop capturing
    try {
        await chrome.runtime.sendMessage({ type: 'stop-capture' });
    } catch {
        // Offscreen may already be gone
    }

    // 2. Disconnect WebSocket (sends stop_session, waits for server ack)
    await disconnectWebSocket();

    // 3. Close offscreen document
    await closeOffscreenDocument();

    const tabId = activeTabId;
    isSessionActive = false;
    activeTabId = null;

    // 4. Notify content script
    if (tabId) {
        chrome.tabs.sendMessage(tabId, { type: 'session-ended' }).catch(() => {});
    }

    console.log('[BG] Session stopped');
}

// ─── Message Handling ───────────────────────────────────────────────

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    // Messages from content script
    if (message.type === 'start-session') {
        startSession(sender.tab.id, message.patient)
            .then(() => sendResponse({ ok: true }))
            .catch(err => sendResponse({ ok: false, error: err.message }));
        return true; // async response
    }

    if (message.type === 'stop-session') {
        stopSession()
            .then(() => sendResponse({ ok: true }))
            .catch(err => sendResponse({ ok: false, error: err.message }));
        return true; // async response
    }

    // Messages from offscreen document or content script (audio)
    if (message.type === 'audio-chunk') {
        sendAudioChunk(message.audio_data, message.source);
        return false;
    }

    if (message.type === 'capture-started') {
        console.log('[BG] Offscreen capture started');
        return false;
    }

    if (message.type === 'capture-error') {
        console.error('[BG] Offscreen capture error:', message.error);
        if (activeTabId) {
            chrome.tabs.sendMessage(activeTabId, {
                type: 'error',
                message: `Audio capture failed: ${message.error}`
            }).catch(() => {});
        }
        stopSession();
        return false;
    }

    // Messages from popup
    if (message.type === 'get-status') {
        sendResponse({
            isSessionActive: isSessionActive,
            activeTabId: activeTabId
        });
        return false;
    }

    if (message.type === 'health-check') {
        (async () => {
            try {
                const serverUrl = message.serverUrl || await getServerUrl();
                const response = await fetch(`${serverUrl}/health`);
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                const data = await response.json();
                sendResponse({ ok: true, data: data });
            } catch (err) {
                sendResponse({ ok: false, error: err.message });
            }
        })();
        return true; // async response
    }

    return false;
});
