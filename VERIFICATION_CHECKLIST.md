# drTranscribe MVP - Verification Checklist

## Pre-Flight Check ✈️

Use this checklist before starting the server.

### 1. File Structure ✅

```bash
# Verify all files exist
ls -1 src/main.py \
     src/websocket_handler.py \
     src/models/patient.py \
     src/models/consultation.py \
     src/models/extraction.py \
     src/models/websocket_messages.py \
     src/services/transcription_service.py \
     src/services/extraction_service.py \
     src/services/session_manager.py \
     src/providers/base.py \
     src/providers/transcription/openai_whisper.py \
     src/providers/extraction/openai_gpt.py \
     src/config/settings.py \
     config/settings.yaml \
     frontend/index.html \
     frontend/app.js \
     frontend/style.css \
     requirements.txt \
     Dockerfile \
     docker-compose.yml \
     .env.example
```

**Expected:** All files listed without errors

### 2. Dependencies Installation ✅

```bash
# Install Python dependencies
pip install -r requirements.txt

# Verify installation
pip list | grep -E "fastapi|uvicorn|openai|pydantic|websockets"
```

**Expected Output:**
```
fastapi                 0.115.6
openai                  1.58.1
pydantic                2.10.5
pydantic-settings       2.7.0
uvicorn                 0.34.0
websockets              14.1
```

### 3. Environment Configuration ✅

```bash
# Check if API key is set
echo $OPENAI_API_KEY

# Or check .env file
cat .env 2>/dev/null | grep OPENAI_API_KEY
```

**Expected:** Your OpenAI API key (starts with `sk-`)

### 4. Python Version ✅

```bash
python --version
# or
python3 --version
```

**Expected:** Python 3.11 or higher

### 5. Port Availability ✅

```bash
# Check if port 8000 is free
lsof -i :8000
```

**Expected:** No output (port is free)

If port is in use:
```bash
# Kill the process using port 8000
lsof -ti :8000 | xargs kill -9

# Or use a different port in config/settings.yaml
```

## Server Startup Check 🚀

### 1. Start Server

```bash
./start.sh
# or
python -m src.main
# or
python3 -m src.main
```

**Expected Output:**
```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### 2. Health Check

In a new terminal:
```bash
curl http://localhost:8000/health
```

**Expected Output:**
```json
{
  "status": "healthy",
  "active_sessions": 0
}
```

### 3. Frontend Access

Open browser to: `http://localhost:8000`

**Expected:** 
- drTranscribe title visible
- Patient form with 3 fields
- Start Recording button (enabled)
- Stop Recording button (disabled)
- 5 extraction sections visible

## Functional Testing 🧪

### Test 1: Patient Form Validation

**Steps:**
1. Leave all fields empty
2. Click "Start Recording"

**Expected:** Alert "Please fill in all patient information fields"

### Test 2: Age Validation

**Steps:**
1. Enter Name: "Test"
2. Enter Age: "999"
3. Enter Gender: "Male"
4. Click "Start Recording"

**Expected:** Alert "Please enter a valid age"

### Test 3: Microphone Permission

**Steps:**
1. Enter valid patient info
2. Click "Start Recording"

**Expected:** 
- Browser prompts for microphone permission
- After allowing: "Recording..." status appears
- Stop button becomes enabled

### Test 4: WebSocket Connection

**With browser DevTools open (F12 → Network → WS):**

**Steps:**
1. Start recording

**Expected:**
- WebSocket connection to `ws://localhost:8000/ws` established
- Status: 101 Switching Protocols

### Test 5: Audio Chunk Transmission

**Steps:**
1. Start recording
2. Speak for 10 seconds
3. Check browser console (F12 → Console)

**Expected:**
- "WebSocket connected" message
- "Sent audio chunk: [size] bytes" messages every 5 seconds

### Test 6: Transcription (Server Logs)

**In server terminal:**

**Steps:**
1. Start recording
2. Speak clearly: "Hello, this is a test"
3. Watch server logs

**Expected:**
```
INFO - Sending [size] bytes to Whisper API
INFO - Transcription successful: [X] characters
INFO - Transcribed: Hello, this is a test...
```

### Test 7: Extraction

**Steps:**
1. Use test consultation script from SETUP_GUIDE.md
2. Speak the full conversation
3. Watch extraction sections in browser

**Expected:**
- Chief Complaint section updates with patient symptoms
- Diagnosis section updates with doctor's assessment
- Medicine section updates with prescriptions
- Advice section updates with lifestyle guidance
- Next Steps section updates with follow-up actions

### Test 8: Real-time Updates

**Steps:**
1. Start recording
2. Say: "The patient complains of headaches"
3. Wait 10 seconds
4. Say: "I diagnose tension headaches"
5. Wait 10 seconds

**Expected:**
- First extraction: Chief Complaint populates
- Second extraction: Chief Complaint persists, Diagnosis populates

### Test 9: Session Stop

**Steps:**
1. Start recording
2. Record for 30 seconds
3. Click "Stop Recording"

**Expected:**
- WebSocket closes
- Status changes to "Ready"
- Start button enabled
- Stop button disabled
- Patient form enabled again

### Test 10: Multiple Sessions

**Steps:**
1. Complete a full recording session
2. Change patient information
3. Start a new recording session

**Expected:**
- Previous extraction sections clear
- New session starts fresh
- No interference between sessions

## Error Scenarios 🔥

### Error 1: API Key Missing

**Steps:**
1. Unset OPENAI_API_KEY
2. Start server

**Expected:**
```
Error: OPENAI_API_KEY environment variable is not set
```

### Error 2: Invalid API Key

**Steps:**
1. Set OPENAI_API_KEY to "invalid"
2. Start recording
3. Try to record

**Expected:**
- Server logs show "Transcription failed"
- Frontend shows error message

### Error 3: Network Timeout

**Steps:**
1. Disconnect internet
2. Start recording
3. Try to record

**Expected:**
- Server logs show API timeout
- Frontend receives error message

### Error 4: WebSocket Disconnection

**Steps:**
1. Start recording
2. Stop server (Ctrl+C)

**Expected:**
- Browser console shows "WebSocket closed"
- Recording stops automatically

## Performance Testing ⚡

### Test 1: Latency Measurement

**Steps:**
1. Start recording
2. Say: "Test message" at exactly 0 seconds
3. Note when extraction appears

**Expected:** 
- Total latency: 5-8 seconds
- Breakdown: 5s buffer + 1-2s transcription + 1-2s extraction

### Test 2: Concurrent Sessions

**Steps:**
1. Open 3 browser windows
2. Start recording in all 3
3. Check server health: `curl http://localhost:8000/health`

**Expected:**
```json
{
  "status": "healthy",
  "active_sessions": 3
}
```

### Test 3: Long Session

**Steps:**
1. Start recording
2. Record continuously for 5 minutes
3. Check extraction sections

**Expected:**
- All sections continue to update
- No memory leaks
- No crashes

## Docker Testing 🐳

### Test 1: Docker Build

```bash
docker-compose build
```

**Expected:**
- Build completes without errors
- Image created: `drtranscribe-mvp`

### Test 2: Docker Run

```bash
export OPENAI_API_KEY=your-key
docker-compose up -d
```

**Expected:**
```
Creating drtranscribe-mvp ... done
```

### Test 3: Docker Health Check

```bash
curl http://localhost:8000/health
```

**Expected:**
```json
{
  "status": "healthy",
  "active_sessions": 0
}
```

### Test 4: Docker Logs

```bash
docker-compose logs -f
```

**Expected:**
- No errors
- Server startup messages visible

## Code Quality Checks ✨

### Check 1: Python Syntax

```bash
python3 -m py_compile src/**/*.py
```

**Expected:** No errors

### Check 2: Import Resolution

```bash
python3 -c "from src.main import app; print('✓ Imports work')"
```

**Expected:** `✓ Imports work`

### Check 3: Configuration Loading

```bash
python3 -c "from src.config.settings import load_settings; s = load_settings(); print('✓ Config loads')"
```

**Expected:** `✓ Config loads`

## Security Checks 🔒

### Check 1: .env in .gitignore

```bash
grep -q "^\.env$" .gitignore && echo "✓ .env is ignored" || echo "✗ .env is NOT ignored"
```

**Expected:** `✓ .env is ignored`

### Check 2: No Hardcoded Keys

```bash
grep -r "sk-" src/ && echo "✗ API key found in code!" || echo "✓ No hardcoded keys"
```

**Expected:** `✓ No hardcoded keys`

### Check 3: CORS Configuration

```bash
grep "allow_origins" src/main.py
```

**Expected:** `allow_origins=["*"]` (Note: Change for production!)

## Final Checklist ✅

Before declaring MVP complete:

- [ ] All files created (22 files)
- [ ] Dependencies install without errors
- [ ] Server starts without errors
- [ ] Health check returns healthy
- [ ] Frontend loads at localhost:8000
- [ ] Patient form validation works
- [ ] Microphone permission requested
- [ ] Audio recording starts
- [ ] WebSocket connection establishes
- [ ] Audio chunks transmitted every 5 seconds
- [ ] Transcription appears in logs
- [ ] Extraction sections update in browser
- [ ] All 5 sections populate correctly
- [ ] Merge logic works (data appends)
- [ ] Stop recording ends session
- [ ] Multiple sessions work sequentially
- [ ] Error messages display properly
- [ ] Docker build succeeds
- [ ] Docker deployment works
- [ ] No hardcoded secrets
- [ ] .env is gitignored

## Troubleshooting Reference 🔧

| Issue | Solution |
|-------|----------|
| Port 8000 in use | `lsof -ti :8000 \| xargs kill -9` |
| Module not found | `pip install -r requirements.txt` |
| Microphone denied | Check browser settings → Microphone |
| WebSocket fails | Check firewall, ensure server running |
| Empty transcription | Speak louder, check microphone |
| No extraction | Check API key, check OpenAI quota |
| Docker fails | Check `.env` file, check Docker running |

## Success Criteria 🎯

MVP is successful when:

1. ✅ Doctor can start recording with patient info
2. ✅ System captures audio in real-time
3. ✅ Transcription happens automatically
4. ✅ Extraction appears within 5-8 seconds
5. ✅ All 5 sections extract correctly
6. ✅ Data merges (doesn't replace)
7. ✅ Session ends cleanly
8. ✅ No crashes or memory leaks
9. ✅ Can switch providers via config
10. ✅ Ready for Groq integration

## Performance Benchmarks 📊

| Metric | Target | How to Measure |
|--------|--------|----------------|
| Latency | 5-8s | Time from speech to extraction display |
| Concurrent sessions | 10+ | Multiple browser windows |
| Session duration | 30+ min | Long continuous recording |
| Memory usage | <500MB | `ps aux \| grep python` |
| CPU usage | <50% | `top` or Activity Monitor |

## Next Steps After Verification ➡️

Once all checks pass:

1. ✅ Mark MVP as complete
2. 🎯 Test with real consultations
3. 📝 Document any issues
4. 🚀 Implement Groq providers
5. 💾 Add database persistence
6. 🔐 Add authentication
7. 📱 Plan mobile app

---

**Use this checklist to verify your drTranscribe MVP is working correctly!**

Each ✅ brings you closer to a production-ready system.
