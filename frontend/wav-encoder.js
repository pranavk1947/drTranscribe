/**
 * WavEncoder - Convert Float32 PCM audio to WAV format
 *
 * Generates complete, standards-compliant WAV files with proper headers.
 * Used for medical-grade audio capture where every chunk must be a
 * valid standalone file.
 *
 * WAV Format:
 * - 44-byte header (RIFF/WAVE format)
 * - Int16 PCM audio data (little-endian)
 * - Mono channel, 16kHz sample rate (Groq recommendation)
 */
class WavEncoder {
    /**
     * Encode Float32 PCM samples to WAV blob
     *
     * @param {Float32Array} samples - Audio samples in range [-1.0, 1.0]
     * @param {number} sampleRate - Sample rate in Hz (e.g., 16000)
     * @param {number} channels - Number of channels (1=mono, 2=stereo)
     * @returns {Blob} Complete WAV file as Blob
     */
    static encode(samples, sampleRate, channels = 1) {
        // Convert Float32 [-1.0, 1.0] to Int16 [-32768, 32767]
        const int16Samples = this.float32ToInt16(samples);

        // Calculate sizes
        const dataLength = int16Samples.length * 2; // 2 bytes per Int16 sample
        const bufferLength = 44 + dataLength;       // 44-byte header + data

        // Create buffer and DataView for writing
        const buffer = new ArrayBuffer(bufferLength);
        const view = new DataView(buffer);

        // Write WAV header (44 bytes)
        this.writeWavHeader(view, sampleRate, channels, dataLength);

        // Write audio data (after 44-byte header)
        const audioData = new Int16Array(buffer, 44);
        audioData.set(int16Samples);

        // Return as Blob with correct MIME type
        return new Blob([buffer], { type: 'audio/wav' });
    }

    /**
     * Convert Float32 samples to Int16 samples
     *
     * Clamps values to [-1.0, 1.0] to prevent clipping/distortion.
     * Critical for medical-grade audio quality.
     *
     * @param {Float32Array} float32Array - Input samples
     * @returns {Int16Array} Converted samples
     */
    static float32ToInt16(float32Array) {
        const int16Array = new Int16Array(float32Array.length);

        for (let i = 0; i < float32Array.length; i++) {
            // Clamp to [-1.0, 1.0] range
            const clamped = Math.max(-1, Math.min(1, float32Array[i]));

            // Scale to Int16 range [-32768, 32767]
            int16Array[i] = clamped < 0
                ? clamped * 0x8000  // -32768
                : clamped * 0x7FFF; // 32767
        }

        return int16Array;
    }

    /**
     * Write 44-byte WAV header to DataView
     *
     * WAV header structure (all values little-endian):
     * Offset  Size  Field           Value
     * ------  ----  --------------  -------------------------
     * 0       4     ChunkID         "RIFF"
     * 4       4     ChunkSize       FileSize - 8
     * 8       4     Format          "WAVE"
     * 12      4     Subchunk1ID     "fmt "
     * 16      4     Subchunk1Size   16 (for PCM)
     * 20      2     AudioFormat     1 (PCM = uncompressed)
     * 22      2     NumChannels     1 (mono) or 2 (stereo)
     * 24      4     SampleRate      16000 (Hz)
     * 28      4     ByteRate        SampleRate * Channels * 2
     * 32      2     BlockAlign      Channels * 2
     * 34      2     BitsPerSample   16
     * 36      4     Subchunk2ID     "data"
     * 40      4     Subchunk2Size   NumSamples * Channels * 2
     *
     * @param {DataView} view - DataView to write to
     * @param {number} sampleRate - Sample rate in Hz
     * @param {number} channels - Number of channels
     * @param {number} dataLength - Length of audio data in bytes
     */
    static writeWavHeader(view, sampleRate, channels, dataLength) {
        const blockAlign = channels * 2; // 2 bytes per sample (Int16)
        const byteRate = sampleRate * blockAlign;

        // "RIFF" chunk descriptor
        this.writeString(view, 0, 'RIFF');
        view.setUint32(4, 36 + dataLength, true); // File size - 8
        this.writeString(view, 8, 'WAVE');

        // "fmt " sub-chunk (format description)
        this.writeString(view, 12, 'fmt ');
        view.setUint32(16, 16, true);        // Subchunk1Size (16 for PCM)
        view.setUint16(20, 1, true);         // AudioFormat (1 = PCM)
        view.setUint16(22, channels, true);  // NumChannels
        view.setUint32(24, sampleRate, true); // SampleRate
        view.setUint32(28, byteRate, true);  // ByteRate
        view.setUint16(32, blockAlign, true); // BlockAlign
        view.setUint16(34, 16, true);        // BitsPerSample

        // "data" sub-chunk (actual audio data)
        this.writeString(view, 36, 'data');
        view.setUint32(40, dataLength, true); // Subchunk2Size
    }

    /**
     * Write ASCII string to DataView
     *
     * @param {DataView} view - DataView to write to
     * @param {number} offset - Byte offset to start writing
     * @param {string} string - ASCII string to write
     */
    static writeString(view, offset, string) {
        for (let i = 0; i < string.length; i++) {
            view.setUint8(offset + i, string.charCodeAt(i));
        }
    }
}

// Export for use in other modules
export default WavEncoder;
