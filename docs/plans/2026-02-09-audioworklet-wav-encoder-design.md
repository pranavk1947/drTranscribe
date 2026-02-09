# AudioWorklet + WAV Encoder Design

**Date:** 2026-02-09
**Status:** Approved
**Purpose:** Replace MediaRecorder with AudioWorklet-based WAV encoder to fix fragmented WebM chunk problem

---

## Problem Statement

Current implementation uses MediaRecorder API which produces:
- **First chunk:** Complete WebM file with headers ✅
- **Subsequent chunks:** Fragmented WebM stream data (no headers) ❌

This causes transcription failures:
```
ERROR - Unknown audio format, header: 47848174
ERROR - [ogg @ 0x...] cannot find sync word
ERROR - ffmpeg returned error code: 183
```

**Root Cause:** MediaRecorder with timesliced recording sends stream fragments, not complete files.

**Impact:**
- Only first chunk transcribes successfully
- All subsequent chunks fail
- Breaks real-time transcription for medical consultations

---

## Solution Overview

Replace MediaRecorder with Web Audio API + AudioWorklet to:
- ✅ Generate complete, standalone WAV files for each chunk
- ✅ Use Groq's recommended format (WAV, 16kHz, mono)
- ✅ Maintain real-time streaming (5-second chunks)
- ✅ Eliminate fragmentation issues
- ✅ Improve audio quality consistency

---

## Architecture

### Component Structure

```
┌─────────────────────────────────────────────────────────────┐
│                     Frontend (Browser)                       │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Microphone                                                   │
│      ↓                                                        │
│  AudioContext (16kHz)                                         │
│      ↓                                                        │
│  MediaStreamSource                                            │
│      ↓                                                        │
│  AudioWorkletNode (audio thread)                              │
│      │                                                        │
│      │ ← audio-worklet-processor.js                           │
│      │   • Buffers samples (5 seconds)                        │
│      │   • Sends Float32Array chunks                          │
│      ↓                                                        │
│  Main Thread                                                  │
│      │                                                        │
│      │ ← audio-recorder.js                                    │
│      │   • Manages AudioContext lifecycle                     │
│      │   • Handles chunk events                               │
│      ↓                                                        │
│  WavEncoder                                                   │
│      │                                                        │
│      │ ← wav-encoder.js                                       │
│      │   • Float32 → Int16 conversion                         │
│      │   • WAV header generation                              │
│      ↓                                                        │
│  Complete WAV Blob                                            │
│      ↓                                                        │
│  WebSocket → Server                                           │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Microphone → AudioContext**
   - getUserMedia() captures audio stream
   - AudioContext resamples to 16kHz mono

2. **AudioContext → AudioWorklet (audio thread)**
   - Real-time audio processing (128-sample frames)
   - Runs on separate thread with real-time priority
   - Buffers samples until chunk duration reached

3. **AudioWorklet → Main Thread**
   - postMessage() sends Float32Array (transferable)
   - Zero-copy transfer for efficiency
   - Includes sample rate metadata

4. **Main Thread → WAV Encoder**
   - Convert Float32 [-1.0, 1.0] to Int16 [-32768, 32767]
   - Add 44-byte WAV header
   - Create Blob with type 'audio/wav'

5. **WAV Blob → WebSocket**
   - Base64 encode
   - Send to server via existing pipeline
   - Server receives complete, valid WAV file

---

## Component Details

### 1. AudioWorklet Processor

**File:** `frontend/audio-worklet-processor.js`

**Purpose:** Capture and buffer audio samples in real-time

**Key Features:**
- Runs on audio rendering thread (real-time priority)
- Processes 128-sample frames at ~128 FPS (for 16kHz)
- Pre-allocated buffer to avoid GC in audio thread
- Efficient sample copying

**Configuration:**
```javascript
{
  sampleRate: 16000,      // Groq recommendation
  chunkDuration: 5,       // Configurable from settings
  channels: 1             // Mono for medical clarity
}
```

**Message Protocol:**
- **Receive:** `{ type: 'configure', sampleRate, chunkDuration }`
- **Send:** `{ type: 'audio-chunk', samples: Float32Array, sampleRate }`

**Performance Considerations:**
- process() called every ~3ms - must be fast
- Use pre-allocated buffers (no allocations in process())
- Transfer Float32Array (zero-copy via Transferable)
- Avoid any blocking operations

**Medical Best Practice:**
- No audio drops - critical for accurate transcription
- Buffer overflow protection (log warning, never lose data)
- Flush partial buffer on stop (capture trailing audio)

---

### 2. WAV Encoder

**File:** `frontend/wav-encoder.js`

**Purpose:** Convert Float32 PCM to complete WAV files

**WAV Header Structure (44 bytes):**
```
Offset  Size  Field              Value
------  ----  -----------------  -------------------------
0       4     ChunkID            "RIFF"
4       4     ChunkSize          FileSize - 8
8       4     Format             "WAVE"
12      4     Subchunk1ID        "fmt "
16      4     Subchunk1Size      16 (for PCM)
20      2     AudioFormat        1 (PCM)
22      2     NumChannels        1 (mono)
24      4     SampleRate         16000
28      4     ByteRate           SampleRate * Channels * 2
32      2     BlockAlign         Channels * 2
34      2     BitsPerSample      16
36      4     Subchunk2ID        "data"
40      4     Subchunk2Size      NumSamples * Channels * 2
44      *     Data               Audio samples (Int16)
```

**Conversion Algorithm:**
```javascript
// Float32 [-1.0, 1.0] → Int16 [-32768, 32767]
function float32ToInt16(float32Array) {
  const int16Array = new Int16Array(float32Array.length);
  for (let i = 0; i < float32Array.length; i++) {
    // Clamp to prevent distortion
    const clamped = Math.max(-1, Math.min(1, float32Array[i]));
    int16Array[i] = clamped * 0x7FFF; // 32767
  }
  return int16Array;
}
```

**Medical Best Practice:**
- Clamp values to prevent clipping/distortion
- Standard WAV format (maximum compatibility)
- Little-endian byte order (WAV specification)
- Complete headers (every chunk is valid standalone file)

---

### 3. AudioRecorder Manager

**File:** `frontend/audio-recorder.js`

**Purpose:** Orchestrate recording lifecycle

**Public API:**
```javascript
class AudioRecorder {
  constructor(stream, config, onChunkReady)
  async start()      // Initialize and start recording
  stop()             // Stop and cleanup
  isRecording()      // Check state
}
```

**Initialization Flow:**
1. Create AudioContext with configured sample rate
2. Load AudioWorklet module via addModule()
3. Create MediaStreamSource from getUserMedia() stream
4. Create AudioWorkletNode with configuration
5. Connect: MediaStreamSource → AudioWorkletNode → destination
6. Configure worklet via port.postMessage()
7. Listen for worklet messages (audio chunks)

**Chunk Handling:**
```javascript
workletNode.port.onmessage = (event) => {
  if (event.data.type === 'audio-chunk') {
    const { samples, sampleRate } = event.data;
    const wavBlob = WavEncoder.encode(samples, sampleRate, 1);
    this.onChunkReady(wavBlob);
  }
};
```

**Cleanup:**
- Flush any remaining buffer (partial chunk)
- Disconnect all audio nodes
- Close AudioContext
- Stop microphone tracks
- Clear references

**Medical Best Practice:**
- Graceful degradation on errors
- Complete cleanup to free resources
- Capture trailing audio on stop (no data loss)
- Clear error messages for troubleshooting

---

## Configuration

### settings.yaml

**Add new section:**
```yaml
audio:
  chunk_duration_seconds: 5  # Real-time chunk duration
  sample_rate: 16000         # Groq recommendation (16kHz)
  channels: 1                # Mono (required for medical clarity)
```

**Rationale:**
- **5 seconds:** Balance between real-time response and chunk overhead
- **16kHz:** Groq Whisper optimized for this rate, sufficient for speech
- **Mono:** Medical consultations are single-speaker, mono reduces file size

### API Endpoint

**Add to `src/main.py`:**
```python
@app.get("/api/config")
async def get_frontend_config():
    """Provide frontend configuration"""
    return {
        "audio": {
            "chunk_duration_seconds": settings.audio.chunk_duration_seconds,
            "sample_rate": settings.audio.sample_rate,
            "channels": settings.audio.channels
        }
    }
```

**Frontend fetch:**
```javascript
const response = await fetch('/api/config');
const config = await response.json();
// Use config.audio.*
```

---

## Integration with Existing Code

### app.js Changes

**Before (MediaRecorder):**
```javascript
mediaRecorder = new MediaRecorder(stream, options);
mediaRecorder.start(30000);
mediaRecorder.ondataavailable = (event) => {
  sendAudioChunk(event.data);
};
```

**After (AudioRecorder):**
```javascript
// Fetch config
const response = await fetch('/api/config');
const config = await response.json();

// Create recorder
audioRecorder = new AudioRecorder(
  stream,
  config.audio,
  (wavBlob) => sendAudioChunk(wavBlob)
);

// Start
await audioRecorder.start();
```

**Keep existing:**
- WebSocket connection logic
- sendAudioChunk() function (already handles Blobs)
- Start/stop UI logic
- Session management

---

## Error Handling

### Browser Compatibility

**Check before initialization:**
```javascript
if (!window.AudioWorklet) {
  alert('AudioWorklet not supported. Please use Chrome 66+, Firefox 76+, or Safari 14.1+');
  return;
}
```

**Supported browsers:**
- Chrome 66+ ✅
- Firefox 76+ ✅
- Safari 14.1+ ✅
- Edge 79+ ✅

### AudioWorklet Loading

**Common issues:**
- CORS errors (worklet must be same-origin)
- Module load failures (check path, server running)

**Solution:**
```javascript
try {
  await audioContext.audioWorklet.addModule('/static/audio-worklet-processor.js');
} catch (error) {
  console.error('Failed to load AudioWorklet:', error);
  alert('Failed to initialize audio system. Please refresh and try again.');
}
```

### Recording Interruptions

**Handle gracefully:**
- Microphone disconnection → stop recording, notify user
- Tab backgrounded → AudioContext.state changes, resume on focus
- Browser audio suspension → detect and handle

**Implementation:**
```javascript
// Detect microphone disconnection
stream.getTracks()[0].onended = () => {
  console.error('Microphone disconnected');
  stopRecording();
  alert('Microphone disconnected. Please reconnect and restart recording.');
};

// Handle AudioContext suspension
audioContext.onstatechange = () => {
  if (audioContext.state === 'suspended') {
    console.warn('AudioContext suspended (tab backgrounded?)');
  }
};
```

### Buffer Overflow Protection

**Should never happen, but:**
```javascript
if (bufferIndex + inputLength > buffer.length) {
  console.error('Buffer overflow detected! This should not happen.');
  // Send current buffer
  // Reset for next chunk
}
```

---

## Medical Best Practices

### Audio Quality Requirements

**For accurate medical transcription:**
- ✅ No audio drops or gaps
- ✅ Consistent sample rate (16kHz)
- ✅ No clipping or distortion
- ✅ Complete chunks (no fragmentation)
- ✅ Reliable error recovery

### Real-Time Requirements

**5-second latency budget:**
- Audio capture: <50ms
- Encoding: <100ms
- WebSocket send: <50ms
- Server processing: <500ms
- Transcription (Groq): ~2-3 seconds
- **Total: ~3-4 seconds end-to-end**

### Data Integrity

**Critical for medical records:**
- Every spoken word captured
- No silent audio drops
- Trailing audio flushed on stop
- Error logs for debugging
- Graceful degradation on failures

---

## Testing Strategy

### Unit Tests

1. **WavEncoder:**
   - Float32 to Int16 conversion accuracy
   - WAV header correctness
   - Blob creation and size validation

2. **AudioWorklet:**
   - Buffer management (fill, flush, reset)
   - Message protocol compliance
   - Edge cases (stop mid-buffer)

### Integration Tests

1. **AudioRecorder:**
   - Start/stop lifecycle
   - Chunk timing accuracy (5 seconds ±100ms)
   - Cleanup completeness
   - Error handling paths

### End-to-End Tests

1. **Full Pipeline:**
   - Record 30-second session (6 chunks)
   - Verify all chunks are complete WAV files
   - Verify all chunks transcribe successfully
   - Check for audio gaps or drops
   - Validate transcription accuracy

2. **Edge Cases:**
   - Stop recording mid-chunk (partial audio)
   - Network interruption during send
   - Microphone disconnect during recording
   - Tab backgrounding and resuming

### Manual Testing Checklist

- [ ] Chrome 66+ - record 60 seconds, verify chunks
- [ ] Firefox 76+ - same test
- [ ] Safari 14.1+ - same test
- [ ] Edge 79+ - same test
- [ ] Microphone disconnect scenario
- [ ] Network disconnection scenario
- [ ] Long recording (10+ minutes)
- [ ] Background tab (audio continues?)

---

## Performance Benchmarks

### Target Metrics

- **Chunk generation time:** <100ms per 5-second chunk
- **Memory usage:** <50MB for 10-minute recording
- **CPU usage (audio thread):** <5% average
- **CPU usage (main thread):** <10% during encoding

### Monitoring

**Add to production:**
```javascript
console.log(`✅ Chunk generated: ${wavBlob.size} bytes in ${encodeTime}ms`);
```

**Track:**
- Chunk size (should be ~160KB for 5s at 16kHz mono)
- Encoding time (should be <100ms)
- Dropped frames (should be 0)

---

## Migration Plan

### Phase 1: Add Configuration
1. Add audio section to `config/settings.yaml`
2. Add `/api/config` endpoint in `src/main.py`
3. Test endpoint returns correct config

### Phase 2: Create Audio Modules
1. Create `frontend/audio-worklet-processor.js`
2. Create `frontend/wav-encoder.js`
3. Create `frontend/audio-recorder.js`
4. Unit test each module independently

### Phase 3: Integrate
1. Update `frontend/app.js` to use AudioRecorder
2. Keep MediaRecorder code commented (rollback option)
3. Test in development environment
4. Verify chunks are complete WAV files

### Phase 4: Validate
1. End-to-end test with real recording
2. Verify all chunks transcribe successfully
3. Check server logs for errors
4. Test edge cases (stop, disconnect, etc.)

### Phase 5: Production
1. Deploy to production
2. Monitor for 24 hours
3. Verify no transcription failures
4. Remove old MediaRecorder code

### Rollback Plan

**If issues arise:**
1. Revert `frontend/app.js` to use MediaRecorder
2. Keep new modules for future retry
3. Investigate root cause
4. Fix and redeploy

---

## Benefits Summary

### Functional Benefits
✅ **Complete WAV files** - Every chunk is valid, standalone
✅ **No fragmentation** - Eliminates WebM streaming issues
✅ **Groq-optimized** - WAV, 16kHz, mono (their recommendation)
✅ **Configurable** - Chunk duration via settings.yaml
✅ **Real-time** - 5-second chunks, ~3-4s total latency

### Technical Benefits
✅ **Performance** - AudioWorklet on separate thread
✅ **Reliability** - No ffmpeg conversion failures
✅ **Clean architecture** - Modular, testable components
✅ **Standards-compliant** - Modern Web Audio API
✅ **Future-proof** - No deprecated APIs

### Medical Benefits
✅ **Accurate transcription** - Complete audio capture
✅ **No data loss** - Trailing audio captured
✅ **Error recovery** - Graceful degradation
✅ **Audit trail** - Logs for debugging
✅ **Professional quality** - Medical-grade reliability

---

## Success Criteria

### Must Have
- [x] Design approved
- [ ] All 6 components implemented (3 new files, 3 modified)
- [ ] All chunks are complete WAV files
- [ ] 100% transcription success rate (no fragmentation errors)
- [ ] No audio drops or gaps
- [ ] End-to-end test passes

### Should Have
- [ ] Unit tests for WavEncoder
- [ ] Integration tests for AudioRecorder
- [ ] Performance benchmarks documented
- [ ] Error handling tested
- [ ] Cross-browser testing complete

### Nice to Have
- [ ] Automated E2E tests
- [ ] Load testing (concurrent recordings)
- [ ] Audio quality metrics
- [ ] Production monitoring dashboard

---

## References

- [Web Audio API Specification](https://www.w3.org/TR/webaudio/)
- [AudioWorklet Documentation](https://developer.mozilla.org/en-US/docs/Web/API/AudioWorklet)
- [WAV File Format Specification](http://soundfile.sapp.org/doc/WaveFormat/)
- [Groq Whisper API Documentation](https://console.groq.com/docs/speech-to-text)

---

**End of Design Document**
