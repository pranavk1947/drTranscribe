/**
 * Offscreen Document - Tab audio capture and encoding
 *
 * Handles:
 * 1. Tab audio capture via chrome.tabCapture streamId
 * 2. Re-routing tab audio to speakers (tabCapture mutes by default)
 * 3. WAV encoding via AudioWorklet + WavEncoder
 * 4. Sending base64 audio chunks to background service worker
 *
 * Note: Mic capture is handled by the content script (content.js),
 * which runs in the page context where mic permission is already granted.
 */

let audioContext = null;
let tabStream = null;
let workletNode = null;
let isCapturing = false;

// Audio config defaults (overridden by backend config)
let targetSampleRate = 16000; // What the backend expects
let chunkDuration = 7;

/**
 * Start tab audio capture
 */
async function startCapture(streamId, audioConfig) {
    if (isCapturing) {
        console.warn('[Offscreen] Already capturing');
        return;
    }

    console.log('[Offscreen] Starting capture with streamId:', streamId);

    // Apply audio config if provided
    if (audioConfig) {
        targetSampleRate = audioConfig.sample_rate || 16000;
        chunkDuration = audioConfig.chunk_duration_seconds || 7;
    }

    try {
        // 1. Get tab audio stream using the streamId from tabCapture
        tabStream = await navigator.mediaDevices.getUserMedia({
            audio: {
                mandatory: {
                    chromeMediaSource: 'tab',
                    chromeMediaSourceId: streamId
                }
            },
            video: false
        });
        console.log('[Offscreen] Tab audio stream acquired');

        // 2. Create AudioContext at NATIVE sample rate (usually 48000Hz)
        //    IMPORTANT: Forcing 16kHz causes Chrome's MediaStreamSource to
        //    produce silence. We capture at native rate and downsample later.
        audioContext = new AudioContext();
        const nativeSampleRate = audioContext.sampleRate;
        console.log(`[Offscreen] AudioContext created at ${nativeSampleRate}Hz (native), target: ${targetSampleRate}Hz`);

        // 3. Create source node for tab audio
        const tabSource = audioContext.createMediaStreamSource(tabStream);

        // 4. CRITICAL: Re-route tab audio to speakers
        //    tabCapture mutes the tab audio by default, so we must
        //    connect the tab source directly to the audio destination
        //    to let the user hear the patient's voice
        tabSource.connect(audioContext.destination);
        console.log('[Offscreen] Tab audio routed to speakers');

        // 5. Load AudioWorklet processor and connect tab source to it
        await audioContext.audioWorklet.addModule('audio-worklet-processor.js');
        workletNode = new AudioWorkletNode(audioContext, 'audio-capture-processor');

        // Configure the worklet with NATIVE sample rate for buffering
        workletNode.port.postMessage({
            type: 'configure',
            sampleRate: nativeSampleRate,
            chunkDuration: chunkDuration
        });

        // Handle audio chunks from worklet
        workletNode.port.onmessage = (event) => {
            if (event.data.type === 'audio-chunk') {
                handleAudioChunk(event.data.samples, event.data.sampleRate);
            }
        };

        // Connect tab source to worklet
        tabSource.connect(workletNode);
        // Worklet needs to connect to destination to keep processing
        workletNode.connect(audioContext.destination);

        isCapturing = true;
        console.log('[Offscreen] Audio capture pipeline active');

        // Notify background
        chrome.runtime.sendMessage({ type: 'capture-started' });

    } catch (err) {
        console.error('[Offscreen] Failed to start capture:', err);
        chrome.runtime.sendMessage({
            type: 'capture-error',
            error: err.message
        });
        stopCapture();
    }
}

/**
 * Downsample audio from native rate to target rate using linear interpolation
 *
 * @param {Float32Array} samples - Audio samples at native rate
 * @param {number} fromRate - Source sample rate (e.g., 48000)
 * @param {number} toRate - Target sample rate (e.g., 16000)
 * @returns {Float32Array} Downsampled audio
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

/**
 * Handle audio chunk from AudioWorklet - downsample, encode to WAV, send to background
 */
function handleAudioChunk(samples, nativeSr) {
    try {
        // Downsample from native rate (48kHz) to target rate (16kHz)
        const downsampled = downsample(samples, nativeSr, targetSampleRate);

        // Encode to WAV at target sample rate
        const wavBlob = WavEncoder.encode(downsampled, targetSampleRate, 1);

        // Convert Blob to base64
        const reader = new FileReader();
        reader.onloadend = () => {
            const base64Data = reader.result.split(',')[1];
            // Send to background service worker
            chrome.runtime.sendMessage({
                type: 'audio-chunk',
                audio_data: base64Data
            });
            console.log(`[Offscreen] Sent audio chunk: ${samples.length} native samples -> ${downsampled.length} @${targetSampleRate}Hz, ${base64Data.length} chars base64`);
        };
        reader.onerror = (err) => {
            console.error('[Offscreen] FileReader error:', err);
        };
        reader.readAsDataURL(wavBlob);
    } catch (err) {
        console.error('[Offscreen] Error encoding audio chunk:', err);
    }
}

/**
 * Stop audio capture and clean up resources
 */
function stopCapture() {
    console.log('[Offscreen] Stopping capture');

    // Flush remaining audio from worklet
    if (workletNode) {
        workletNode.port.postMessage({ type: 'flush' });
        workletNode.disconnect();
        workletNode = null;
    }

    // Stop tab stream tracks
    if (tabStream) {
        tabStream.getTracks().forEach(track => track.stop());
        tabStream = null;
    }

    // Close audio context
    if (audioContext) {
        audioContext.close().catch(() => {});
        audioContext = null;
    }

    isCapturing = false;
    console.log('[Offscreen] Capture stopped and cleaned up');
}

/**
 * Listen for messages from background service worker
 */
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === 'start-capture') {
        startCapture(message.streamId, message.audioConfig);
        sendResponse({ ok: true });
    } else if (message.type === 'stop-capture') {
        stopCapture();
        sendResponse({ ok: true });
    }
    return false;
});
