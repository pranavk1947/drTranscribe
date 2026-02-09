/**
 * AudioRecorder - Manage AudioWorklet-based audio recording
 *
 * Orchestrates the audio capture pipeline:
 * 1. Initialize AudioContext and AudioWorklet
 * 2. Connect microphone stream to worklet
 * 3. Handle audio chunks from worklet
 * 4. Encode chunks to WAV format
 * 5. Callback with complete WAV blobs
 *
 * Replaces MediaRecorder with medical-grade audio capture.
 */
import WavEncoder from './wav-encoder.js';

class AudioRecorder {
    /**
     * Create AudioRecorder instance
     *
     * @param {MediaStream} stream - Microphone stream from getUserMedia()
     * @param {Object} config - Audio configuration
     * @param {number} config.sample_rate - Sample rate in Hz (e.g., 16000)
     * @param {number} config.chunk_duration_seconds - Chunk duration (e.g., 5)
     * @param {number} config.channels - Number of channels (1=mono)
     * @param {Function} onChunkReady - Callback(wavBlob) when chunk ready
     */
    constructor(stream, config, onChunkReady) {
        this.stream = stream;
        this.config = config;
        this.onChunkReady = onChunkReady;

        // Audio components (initialized in start())
        this.audioContext = null;
        this.sourceNode = null;
        this.workletNode = null;

        // State
        this.recording = false;
    }

    /**
     * Start audio recording
     *
     * Initializes AudioContext, loads AudioWorklet, and starts capture.
     *
     * @throws {Error} If AudioWorklet not supported or initialization fails
     */
    async start() {
        if (this.recording) {
            console.warn('[AudioRecorder] Already recording');
            return;
        }

        try {
            // Check browser support
            if (!window.AudioWorklet) {
                throw new Error('AudioWorklet not supported. Please use Chrome 66+, Firefox 76+, or Safari 14.1+');
            }

            console.log('[AudioRecorder] Starting...');
            console.log(`[AudioRecorder] Config: ${this.config.sample_rate}Hz, ${this.config.chunk_duration_seconds}s chunks, ${this.config.channels} channel(s)`);

            // Create AudioContext with configured sample rate
            this.audioContext = new AudioContext({
                sampleRate: this.config.sample_rate,
                latencyHint: 'interactive' // Low latency for real-time
            });

            console.log(`[AudioRecorder] AudioContext created: ${this.audioContext.sampleRate}Hz`);

            // Load AudioWorklet module
            await this.audioContext.audioWorklet.addModule('/static/audio-worklet-processor.js');
            console.log('[AudioRecorder] AudioWorklet module loaded');

            // Create audio source from microphone stream
            this.sourceNode = this.audioContext.createMediaStreamSource(this.stream);

            // Create AudioWorklet node
            this.workletNode = new AudioWorkletNode(
                this.audioContext,
                'audio-capture-processor'
            );

            // Configure worklet
            this.workletNode.port.postMessage({
                type: 'configure',
                sampleRate: this.config.sample_rate,
                chunkDuration: this.config.chunk_duration_seconds
            });

            // Listen for audio chunks from worklet
            this.workletNode.port.onmessage = (event) => {
                this.handleWorkletMessage(event.data);
            };

            // Connect audio graph: Microphone → Worklet → Destination
            this.sourceNode.connect(this.workletNode);
            this.workletNode.connect(this.audioContext.destination);

            this.recording = true;
            console.log('[AudioRecorder] Recording started');

        } catch (error) {
            console.error('[AudioRecorder] Failed to start:', error);
            this.cleanup();
            throw error;
        }
    }

    /**
     * Stop audio recording
     *
     * Flushes any remaining buffered audio and cleans up resources.
     */
    stop() {
        if (!this.recording) {
            console.warn('[AudioRecorder] Not recording');
            return;
        }

        console.log('[AudioRecorder] Stopping...');

        // Request worklet to flush any remaining buffer
        if (this.workletNode) {
            this.workletNode.port.postMessage({ type: 'flush' });
        }

        // Small delay to allow flush to complete
        setTimeout(() => {
            this.cleanup();
            this.recording = false;
            console.log('[AudioRecorder] Recording stopped');
        }, 100);
    }

    /**
     * Check if currently recording
     *
     * @returns {boolean} true if recording
     */
    isRecording() {
        return this.recording;
    }

    /**
     * Handle messages from AudioWorklet
     *
     * @param {Object} data - Message data
     */
    handleWorkletMessage(data) {
        if (data.type === 'audio-chunk') {
            this.handleAudioChunk(data.samples, data.sampleRate);
        }
    }

    /**
     * Handle audio chunk from worklet
     *
     * Encodes Float32 samples to WAV and calls callback.
     *
     * @param {Float32Array} samples - Audio samples
     * @param {number} sampleRate - Sample rate in Hz
     */
    handleAudioChunk(samples, sampleRate) {
        try {
            console.log(`[AudioRecorder] Encoding chunk: ${samples.length} samples (${(samples.length / sampleRate).toFixed(2)}s)`);

            const startTime = performance.now();

            // Encode to WAV
            const wavBlob = WavEncoder.encode(
                samples,
                sampleRate,
                this.config.channels
            );

            const encodeTime = performance.now() - startTime;
            console.log(`[AudioRecorder] Chunk encoded: ${wavBlob.size} bytes in ${encodeTime.toFixed(1)}ms`);

            // Call callback with WAV blob
            if (this.onChunkReady) {
                this.onChunkReady(wavBlob);
            }

        } catch (error) {
            console.error('[AudioRecorder] Failed to encode chunk:', error);
        }
    }

    /**
     * Cleanup audio resources
     *
     * Disconnects all nodes and closes AudioContext.
     */
    cleanup() {
        console.log('[AudioRecorder] Cleaning up...');

        // Disconnect audio nodes
        if (this.sourceNode) {
            this.sourceNode.disconnect();
            this.sourceNode = null;
        }

        if (this.workletNode) {
            this.workletNode.disconnect();
            this.workletNode = null;
        }

        // Close AudioContext
        if (this.audioContext) {
            this.audioContext.close();
            this.audioContext = null;
        }
    }
}

export default AudioRecorder;
