/**
 * Offscreen Document - All audio capture and encoding for drTranscribe
 *
 * Handles:
 * 1. Microphone capture via getUserMedia (doctor / ambient audio)
 * 2. Tab audio capture via chrome.tabCapture streamId (patient audio, dual mode)
 * 3. Re-routing tab audio to speakers (tabCapture mutes by default)
 * 4. WAV encoding via AudioWorklet + WavEncoder
 * 5. Sending base64 audio chunks to background service worker
 *
 * Modes:
 * - "ambient": mic only, chunks tagged source: "ambient"
 * - "dual":    mic (source: "mic") + tab audio (source: "tab")
 *
 * Messages from background (all carry target: "offscreen"):
 * - offscreen-start-capture { mode, streamId?, audioConfig }
 * - offscreen-stop-capture
 * - offscreen-pause-capture / offscreen-resume-capture
 * - offscreen-restart-tab { streamId }   (re-capture after tab loss)
 * - offscreen-restart-mic                (re-capture after mic loss)
 *
 * Messages to background:
 * - audio-chunk { audio_data, source }
 * - capture-started
 * - capture-error { which: 'mic'|'tab', error }   (chunk encoding failed mid-session)
 * - capture-ended { which: 'mic'|'tab' }   (track ended mid-session)
 *
 * Stop ordering (P1-4): offscreen-stop-capture flushes the worklets
 * (request/response via 'flush' → 'flush-done'), waits for in-flight chunk
 * encodes to reach the background, and only then tears down + responds —
 * so the final partial chunk is sent before background emits stop_session.
 */

let currentMode = null;       // 'ambient' | 'dual'
let isCapturing = false;
let isPaused = false;

// Audio config defaults (overridden by backend config)
let targetSampleRate = 16000;
let chunkDuration = 5;

// Mic pipeline
let micStream = null;
let micContext = null;
let micWorklet = null;

// Tab pipeline
let tabStream = null;
let tabContext = null;
let tabWorklet = null;
let echoAudioElement = null;

// Mic level meter + self-mute (mic only; tab/patient audio is unaffected)
let micMuted = false;
let micAnalyser = null;
let micLevelTimer = null;

/**
 * Check if audio samples contain speech-level energy.
 */
function hasSpeechEnergy(samples, threshold = 0.01) {
    let sumSq = 0;
    for (let i = 0; i < samples.length; i++) {
        sumSq += samples[i] * samples[i];
    }
    const rms = Math.sqrt(sumSq / samples.length);
    return rms >= threshold;
}

/**
 * Downsample audio from native rate to target rate using linear interpolation
 */
function downsample(samples, fromRate, toRate) {
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

// Promises for chunk encodes still in flight (FileReader is async) — awaited
// during stopCapture so the final partial chunk reaches the background
// before the stop ack (P1-4).
let inFlightChunkSends = new Set();

/**
 * Handle an audio chunk from a worklet: downsample, VAD, WAV-encode,
 * base64, send to background with the given source label.
 */
function handleAudioChunk(samples, nativeRate, source) {
    if (isPaused) return; // Drop chunks while session is paused
    try {
        const downsampled = downsample(samples, nativeRate, targetSampleRate);

        // Voice Activity Detection: skip silent/noise-only chunks
        if (!hasSpeechEnergy(downsampled)) return;

        const wavBlob = WavEncoder.encode(downsampled, targetSampleRate, 1);

        const sendPromise = new Promise((resolve) => {
            const reader = new FileReader();
            reader.onloadend = () => {
                const base64Data = reader.result.split(',')[1];
                Promise.resolve(chrome.runtime.sendMessage({
                    type: 'audio-chunk',
                    audio_data: base64Data,
                    source: source
                })).catch(() => {}).then(resolve);
            };
            reader.onerror = (err) => {
                console.error('[Offscreen] FileReader error:', err);
                resolve();
            };
            reader.readAsDataURL(wavBlob);
        });
        inFlightChunkSends.add(sendPromise);
        sendPromise.then(() => inFlightChunkSends.delete(sendPromise));
    } catch (err) {
        console.error('[Offscreen] Error encoding audio chunk:', err);
        // Non-track pipeline failure — let the background surface it instead
        // of losing audio silently (P2-1).
        chrome.runtime.sendMessage({
            type: 'capture-error',
            which: source === 'tab' ? 'tab' : 'mic',
            error: err.message
        }).catch(() => {});
    }
}

/**
 * Build a capture pipeline for a MediaStream:
 * source -> anti-alias lowpass -> AudioWorklet -> destination.
 * Returns { context, worklet }.
 */
async function buildPipeline(stream, sourceLabel) {
    // AudioContext at NATIVE sample rate (forcing 16kHz produces silence
    // from MediaStreamSource in Chrome) — downsample later.
    const context = new AudioContext();
    const nativeRate = context.sampleRate;
    console.log(`[Offscreen] ${sourceLabel} AudioContext at ${nativeRate}Hz, target ${targetSampleRate}Hz`);

    const source = context.createMediaStreamSource(stream);

    // Anti-alias filter: remove frequencies above target Nyquist (8kHz)
    // before downsampling. Prevents aliasing artifacts in the speech band.
    const antiAliasFilter = context.createBiquadFilter();
    antiAliasFilter.type = 'lowpass';
    antiAliasFilter.frequency.value = 7500;
    antiAliasFilter.Q.value = 0.707; // Butterworth — flat passband

    await context.audioWorklet.addModule('audio-worklet-processor.js');
    const worklet = new AudioWorkletNode(context, 'audio-capture-processor');

    worklet.port.postMessage({
        type: 'configure',
        sampleRate: nativeRate,
        chunkDuration: chunkDuration
    });

    worklet.port.onmessage = (event) => {
        if (event.data.type === 'audio-chunk') {
            handleAudioChunk(event.data.samples, event.data.sampleRate, sourceLabel);
        }
    };

    source.connect(antiAliasFilter);
    antiAliasFilter.connect(worklet);
    // Worklet must connect to destination to keep processing
    worklet.connect(context.destination);

    return { context, worklet, source };
}

/**
 * Notify background that a track ended mid-session (tab closed/navigated,
 * mic unplugged). Background auto-pauses the session.
 */
function notifyCaptureEnded(which) {
    if (!isCapturing) return; // Expected during stopCapture cleanup
    console.warn(`[Offscreen] ${which} track ended unexpectedly`);
    chrome.runtime.sendMessage({ type: 'capture-ended', which: which }).catch(() => {});
}

/**
 * Start microphone capture. Source label depends on mode:
 * ambient -> "ambient", dual -> "mic".
 * Returns { ok } or { ok: false, which: 'mic', name, error }.
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
    } catch (err) {
        console.warn('[Offscreen] Mic getUserMedia failed:', err.name, err.message);
        return { ok: false, which: 'mic', name: err.name, error: err.message };
    }

    const micSource = currentMode === 'ambient' ? 'ambient' : 'mic';
    const pipeline = await buildPipeline(micStream, micSource);
    micContext = pipeline.context;
    micWorklet = pipeline.worklet;

    const track = micStream.getAudioTracks()[0];
    if (track) track.onended = () => notifyCaptureEnded('mic');

    // Fresh mic stream starts unmuted; tap it with an analyser to drive the
    // panel's live level meter.
    micMuted = false;
    if (track) track.enabled = true;
    startMicMeter(pipeline.context, pipeline.source);

    console.log(`[Offscreen] Mic capture started (source: ${micSource})`);
    return { ok: true };
}

/**
 * Tap the mic source with an AnalyserNode and stream a normalized 0..1 level
 * to the background ~12x/sec for the panel's waveform. Sends 0 while paused or
 * muted so the bars go flat.
 */
function startMicMeter(context, source) {
    stopMicMeter();
    try {
        micAnalyser = context.createAnalyser();
        micAnalyser.fftSize = 256;
        micAnalyser.smoothingTimeConstant = 0.4;
        source.connect(micAnalyser);
    } catch (err) {
        console.warn('[Offscreen] Could not create mic analyser:', err.message);
        micAnalyser = null;
        return;
    }
    const buf = new Uint8Array(micAnalyser.fftSize);
    micLevelTimer = setInterval(() => {
        if (!micAnalyser) return;
        let level = 0;
        if (isCapturing && !isPaused && !micMuted) {
            micAnalyser.getByteTimeDomainData(buf);
            let sumSq = 0;
            for (let i = 0; i < buf.length; i++) {
                const v = (buf[i] - 128) / 128;
                sumSq += v * v;
            }
            const rms = Math.sqrt(sumSq / buf.length);
            level = Math.min(1, rms * 3.2); // gentle gain so normal speech fills the bars
        }
        chrome.runtime.sendMessage({ type: 'mic-level', level, muted: micMuted }).catch(() => {});
    }, 80);
}

function stopMicMeter() {
    if (micLevelTimer) { clearInterval(micLevelTimer); micLevelTimer = null; }
    if (micAnalyser) { try { micAnalyser.disconnect(); } catch {} micAnalyser = null; }
}

/**
 * Start tab audio capture from a tabCapture streamId (dual mode only).
 * Also re-routes tab audio to speakers, since tabCapture mutes the tab.
 * Returns { ok } or { ok: false, which: 'tab', name, error }.
 */
async function startTabCapture(streamId) {
    try {
        tabStream = await navigator.mediaDevices.getUserMedia({
            audio: {
                mandatory: {
                    chromeMediaSource: 'tab',
                    chromeMediaSourceId: streamId
                }
            },
            video: false
        });
    } catch (err) {
        console.warn('[Offscreen] Tab getUserMedia failed:', err.name, err.message);
        return { ok: false, which: 'tab', name: err.name, error: err.message };
    }

    const pipeline = await buildPipeline(tabStream, 'tab');
    tabContext = pipeline.context;
    tabWorklet = pipeline.worklet;

    // CRITICAL: Re-route tab audio to speakers via <audio> element.
    // tabCapture mutes the tab by default. Routing through a
    // MediaStreamDestination -> <audio> element (NOT context.destination)
    // lets Chrome's AEC correlate playback with mic input and cancel echo.
    const speakerDest = tabContext.createMediaStreamDestination();
    pipeline.source.connect(speakerDest);

    echoAudioElement = document.createElement('audio');
    echoAudioElement.srcObject = speakerDest.stream;
    echoAudioElement.autoplay = true;
    document.body.appendChild(echoAudioElement);

    const track = tabStream.getAudioTracks()[0];
    if (track) track.onended = () => notifyCaptureEnded('tab');

    console.log('[Offscreen] Tab capture started (audio re-routed to speakers)');
    return { ok: true };
}

/**
 * Start capture for a session.
 */
async function startCapture(mode, streamId, audioConfig) {
    if (isCapturing) {
        console.warn('[Offscreen] Already capturing');
        return { ok: true };
    }

    currentMode = mode;
    if (audioConfig) {
        targetSampleRate = audioConfig.sample_rate || 16000;
        chunkDuration = audioConfig.chunk_duration_seconds || 5;
    }

    // 1. Mic (required in both modes)
    const micResult = await startMicCapture();
    if (!micResult.ok) {
        await stopCapture();
        return micResult;
    }

    // 2. Tab audio (dual mode only)
    if (mode === 'dual' && streamId) {
        const tabResult = await startTabCapture(streamId);
        if (!tabResult.ok) {
            await stopCapture();
            return tabResult;
        }
    }

    isCapturing = true;
    isPaused = false;
    chrome.runtime.sendMessage({ type: 'capture-started' }).catch(() => {});
    console.log(`[Offscreen] Capture active (mode: ${mode})`);
    return { ok: true };
}

/**
 * Ask a worklet to flush its partial buffer and wait for the 'flush-done'
 * reply (capped) so the chunk is handed to handleAudioChunk before the
 * pipeline is torn down (P1-4).
 */
function flushWorklet(worklet, timeoutMs = 250) {
    return new Promise((resolve) => {
        if (!worklet) return resolve();
        const prevHandler = worklet.port.onmessage;
        const timer = setTimeout(() => {
            worklet.port.onmessage = prevHandler;
            resolve();
        }, timeoutMs);
        worklet.port.onmessage = (event) => {
            if (event.data.type === 'flush-done') {
                clearTimeout(timer);
                worklet.port.onmessage = prevHandler;
                resolve();
            } else if (prevHandler) {
                prevHandler(event); // e.g. the flushed audio-chunk itself
            }
        };
        worklet.port.postMessage({ type: 'flush' });
    });
}

function stopMicPipeline() {
    stopMicMeter();
    if (micWorklet) {
        // Flushing is handled (awaited) in stopCapture; a fire-and-forget
        // flush here would race teardown / emit a stray post-stop chunk.
        micWorklet.disconnect();
        micWorklet = null;
    }
    if (micStream) {
        micStream.getAudioTracks().forEach(t => { t.onended = null; });
        micStream.getTracks().forEach(t => t.stop());
        micStream = null;
    }
    if (micContext) {
        micContext.close().catch(() => {});
        micContext = null;
    }
}

function stopTabPipeline() {
    if (tabWorklet) {
        tabWorklet.disconnect();
        tabWorklet = null;
    }
    if (echoAudioElement) {
        echoAudioElement.pause();
        echoAudioElement.srcObject = null;
        echoAudioElement.remove();
        echoAudioElement = null;
    }
    if (tabStream) {
        tabStream.getAudioTracks().forEach(t => { t.onended = null; });
        tabStream.getTracks().forEach(t => t.stop());
        tabStream = null;
    }
    if (tabContext) {
        tabContext.close().catch(() => {});
        tabContext = null;
    }
}

/**
 * Stop all capture and clean up resources.
 *
 * P1-4: before tearing the pipelines down, flush the worklets' partial
 * buffers and wait for any in-flight chunk encodes to be forwarded to the
 * background — so the doctor's last utterance is sent before stop_session.
 */
async function stopCapture() {
    console.log('[Offscreen] Stopping capture');
    isCapturing = false; // Set first so onended handlers don't fire notifications

    // 1. Flush partial buffers (request/response, ~250ms cap per worklet)
    await Promise.all([flushWorklet(micWorklet), flushWorklet(tabWorklet)]);

    // 2. Wait for in-flight encodes to reach the background (capped)
    await Promise.race([
        Promise.all([...inFlightChunkSends]),
        new Promise((r) => setTimeout(r, 500))
    ]);

    stopMicPipeline();
    stopTabPipeline();
    isPaused = false;
    currentMode = null;
}

/**
 * Listen for messages from background service worker
 */
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.target !== 'offscreen') return false;

    switch (message.type) {
        case 'offscreen-start-capture':
            startCapture(message.mode, message.streamId, message.audioConfig)
                .then(sendResponse)
                .catch(err => sendResponse({ ok: false, error: err.message }));
            return true; // async response

        case 'offscreen-stop-capture':
            // Async: flushes the final partial chunk to the background before
            // acking, so background sends it ahead of stop_session (P1-4)
            stopCapture()
                .then(() => sendResponse({ ok: true }))
                .catch(err => sendResponse({ ok: false, error: err.message }));
            return true; // async response

        case 'offscreen-set-mute': {
            // Self-mute: disable only the mic track (tab/patient audio keeps
            // flowing in dual mode). Disabled track emits silence, which the
            // backend drops, so no muted audio is transcribed.
            micMuted = !!message.muted;
            const t = micStream && micStream.getAudioTracks()[0];
            if (t) t.enabled = !micMuted;
            console.log('[Offscreen] Mic', micMuted ? 'muted' : 'unmuted');
            sendResponse({ ok: true, muted: micMuted });
            return false;
        }

        case 'offscreen-pause-capture':
            isPaused = true;
            console.log('[Offscreen] Paused (chunks will be dropped)');
            sendResponse({ ok: true });
            return false;

        case 'offscreen-resume-capture':
            isPaused = false;
            console.log('[Offscreen] Resumed');
            sendResponse({ ok: true });
            return false;

        case 'offscreen-restart-tab':
            // Re-capture tab audio after the original tab was closed/navigated
            stopTabPipeline();
            startTabCapture(message.streamId)
                .then(sendResponse)
                .catch(err => sendResponse({ ok: false, which: 'tab', error: err.message }));
            return true; // async response

        case 'offscreen-restart-mic':
            // Re-capture mic after device loss
            stopMicPipeline();
            startMicCapture()
                .then(sendResponse)
                .catch(err => sendResponse({ ok: false, which: 'mic', error: err.message }));
            return true; // async response
    }
    return false;
});
