/**
 * AudioWorkletProcessor - Real-time audio capture and buffering
 *
 * Runs on dedicated audio rendering thread with real-time priority.
 * Captures 128-sample frames at ~128 FPS and buffers until chunk duration reached.
 *
 * Performance critical: This runs every ~3ms, must be extremely fast.
 * No allocations in process() method to avoid garbage collection pauses.
 *
 * Message Protocol:
 * - Receive: { type: 'configure', sampleRate, chunkDuration }
 * - Send: { type: 'audio-chunk', samples: Float32Array, sampleRate }
 */
class AudioCaptureProcessor extends AudioWorkletProcessor {
    constructor() {
        super();

        // Configuration (set via message)
        this.sampleRate = 16000;
        this.chunkDuration = 5;

        // Buffer management
        this.buffer = null;
        this.bufferIndex = 0;
        this.bufferSize = 0;

        // Listen for configuration messages
        this.port.onmessage = (event) => {
            if (event.data.type === 'configure') {
                this.configure(event.data.sampleRate, event.data.chunkDuration);
            } else if (event.data.type === 'flush') {
                this.flush();
            }
        };

        // Initial configuration (will be overridden by configure message)
        this.configure(this.sampleRate, this.chunkDuration);
    }

    /**
     * Configure audio capture parameters
     *
     * @param {number} sampleRate - Sample rate in Hz (e.g., 16000)
     * @param {number} chunkDuration - Chunk duration in seconds (e.g., 5)
     */
    configure(sampleRate, chunkDuration) {
        this.sampleRate = sampleRate;
        this.chunkDuration = chunkDuration;

        // Calculate buffer size: duration * sample rate
        // For 5 seconds at 16kHz: 5 * 16000 = 80,000 samples
        this.bufferSize = this.chunkDuration * this.sampleRate;

        // Pre-allocate buffer (avoid allocations in process())
        this.buffer = new Float32Array(this.bufferSize);
        this.bufferIndex = 0;

        console.log(`[AudioWorklet] Configured: ${this.sampleRate}Hz, ${this.chunkDuration}s chunks, buffer size: ${this.bufferSize} samples`);
    }

    /**
     * Process audio frames (called by browser ~128 times per second)
     *
     * PERFORMANCE CRITICAL: This runs every ~3ms on audio thread.
     * - No allocations (use pre-allocated buffer)
     * - No blocking operations
     * - Fast sample copying only
     *
     * @param {Float32Array[][]} inputs - Input audio data [input][channel][sample]
     * @param {Float32Array[][]} outputs - Output audio data (unused, we're capturing)
     * @param {Object} parameters - Audio parameters (unused)
     * @returns {boolean} true to keep processor alive
     */
    process(inputs, outputs, parameters) {
        // Get first input's first channel (mono)
        const input = inputs[0];
        if (!input || !input.length) {
            return true; // Keep processor alive even with no input
        }

        const inputChannel = input[0];
        if (!inputChannel) {
            return true;
        }

        // Copy samples to buffer
        const inputLength = inputChannel.length;
        const remainingSpace = this.bufferSize - this.bufferIndex;

        if (inputLength <= remainingSpace) {
            // Normal case: samples fit in current buffer
            this.buffer.set(inputChannel, this.bufferIndex);
            this.bufferIndex += inputLength;

            // Check if buffer is full
            if (this.bufferIndex >= this.bufferSize) {
                this.sendChunk();
                this.bufferIndex = 0; // Reset for next chunk
            }
        } else {
            // Edge case: samples overflow buffer (shouldn't happen with 128-sample frames)
            console.warn(`[AudioWorklet] Buffer overflow: ${inputLength} samples, ${remainingSpace} space remaining`);

            // Fill remaining buffer
            this.buffer.set(inputChannel.subarray(0, remainingSpace), this.bufferIndex);
            this.sendChunk();

            // Start new buffer with overflow samples
            const overflow = inputLength - remainingSpace;
            this.buffer.set(inputChannel.subarray(remainingSpace), 0);
            this.bufferIndex = overflow;
        }

        return true; // Keep processor alive
    }

    /**
     * Send buffered audio chunk to main thread
     *
     * Uses transferable Float32Array for zero-copy transfer.
     * After transfer, original buffer is neutered (unusable).
     * Must create new buffer for next chunk.
     */
    sendChunk() {
        // Create copy for transfer (original buffer will be neutered)
        const chunkData = this.buffer.slice(0, this.bufferIndex);

        // Send to main thread (zero-copy transfer)
        this.port.postMessage(
            {
                type: 'audio-chunk',
                samples: chunkData,
                sampleRate: this.sampleRate
            },
            [chunkData.buffer] // Transfer ownership (zero-copy)
        );

        console.log(`[AudioWorklet] Sent chunk: ${this.bufferIndex} samples (${(this.bufferIndex / this.sampleRate).toFixed(2)}s)`);
    }

    /**
     * Flush any remaining buffered audio
     *
     * Called when recording stops mid-buffer.
     * Ensures no audio is lost (critical for medical records).
     */
    flush() {
        if (this.bufferIndex > 0) {
            console.log(`[AudioWorklet] Flushing partial buffer: ${this.bufferIndex} samples`);
            this.sendChunk();
            this.bufferIndex = 0;
        }
    }
}

// Register processor (required by AudioWorklet API)
registerProcessor('audio-capture-processor', AudioCaptureProcessor);
