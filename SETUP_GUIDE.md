# drTranscribe MVP - Setup Guide

## Quick Setup (5 minutes)

### Step 1: Install Dependencies

```bash
cd drTranscribe
pip install -r requirements.txt
```

### Step 2: Set OpenAI API Key

**Option A: Environment Variable (Recommended for testing)**
```bash
export OPENAI_API_KEY=sk-your-api-key-here
```

**Option B: .env File (Recommended for development)**
```bash
cp .env.example .env
# Edit .env and add your key:
# OPENAI_API_KEY=sk-your-api-key-here
```

### Step 3: Run the Application

```bash
# Using the startup script
./start.sh

# Or directly
python -m src.main
```

### Step 4: Test the Application

1. Open your browser to `http://localhost:8000`
2. Fill in patient information:
   - Name: Test Patient
   - Age: 45
   - Gender: Male
3. Click "Start Recording"
4. Allow microphone access when prompted
5. Speak a test consultation (example below)
6. Watch the extraction sections update in real-time
7. Click "Stop Recording" to end

## Test Consultation Script

Use this script to test the system:

```
Doctor: Hello, how can I help you today?
Patient: I've been having severe headaches for the past week.
Doctor: I see. On a scale of 1 to 10, how would you rate the pain?
Patient: It's about an 8, very painful.
Doctor: Based on your symptoms, I believe you're experiencing tension headaches, possibly stress-related.
Patient: What should I do about it?
Doctor: I'm going to prescribe Ibuprofen 400mg, take it twice daily with food.
Patient: Okay.
Doctor: Also, I'd advise you to reduce screen time, take regular breaks, and practice relaxation techniques.
Patient: Anything else?
Doctor: Yes, I'd like you to get a blood test done and come back in two weeks for a follow-up.
Patient: Thank you, doctor.
```

Expected extraction:
- **Chief Complaint**: Severe headaches for the past week, pain level 8/10
- **Diagnosis**: Tension headaches, possibly stress-related
- **Medicine**: Ibuprofen 400mg, twice daily with food
- **Advice**: Reduce screen time, take regular breaks, practice relaxation techniques
- **Next Steps**: Blood test, follow-up in two weeks

## Health Check

Verify the server is running:

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "healthy",
  "active_sessions": 0
}
```

## Troubleshooting

### Issue: "OPENAI_API_KEY not set"

**Solution**: Set the environment variable or create a .env file:
```bash
export OPENAI_API_KEY=your-key-here
```

### Issue: "Module not found"

**Solution**: Ensure you're in the drTranscribe directory and dependencies are installed:
```bash
pip install -r requirements.txt
```

### Issue: "Microphone permission denied"

**Solution**: 
- Chrome: Go to Settings → Privacy & Security → Site Settings → Microphone
- Ensure localhost has permission
- Try accessing via https://localhost:8000 (may require cert)

### Issue: "WebSocket connection failed"

**Solution**: 
- Check if server is running on port 8000
- Check firewall settings
- Ensure no other service is using port 8000

### Issue: "Empty transcription"

**Solution**:
- Speak louder and clearer
- Check microphone is working (test in system settings)
- Ensure 5-second chunks contain audio

### Issue: "Extraction not updating"

**Solution**:
- Check server logs in `logs/drTranscribe.log`
- Verify OPENAI_API_KEY is valid
- Check OpenAI API quota/limits

## Docker Deployment

### Build and Run

```bash
# Build the image
docker-compose build

# Run the container
docker-compose up -d

# Check logs
docker-compose logs -f

# Stop the container
docker-compose down
```

### Docker Environment Variables

Create a `.env` file in the project root:
```bash
OPENAI_API_KEY=sk-your-api-key-here
```

## Production Considerations

### HTTPS Setup (Required for microphone in production)

Browsers require HTTPS for microphone access (except localhost). Options:

1. **Nginx Reverse Proxy with Let's Encrypt**
2. **Cloudflare SSL**
3. **Self-signed certificate** (testing only)

### Environment Variables

For production, use secrets management:
- AWS Secrets Manager
- HashiCorp Vault
- Kubernetes Secrets

### Monitoring

Add monitoring for:
- WebSocket connection failures
- API timeouts
- Transcription errors
- Memory usage

### Scaling

For production scale:
- Use Redis for session storage (replace in-memory)
- Load balancer for multiple instances
- WebSocket sticky sessions
- Horizontal pod autoscaling (Kubernetes)

## Cost Management

### MVP Budget (OpenAI)

Based on 1000 consultations/month (10 min average):
- Whisper API: ~$60/month
- GPT-4 API: ~$55/month
- **Total: ~$115/month**

### Future Optimization (Groq)

After implementing Groq providers:
- Whisper API: ~$12/month (5x cheaper)
- Llama 3 API: ~$0.35/month (150x cheaper)
- **Total: ~$12/month (90% savings!)**

## Next Steps

1. **Test with real consultations** - Validate extraction quality
2. **Implement Groq providers** - Reduce costs by 90%
3. **Add persistence** - PostgreSQL for consultation history
4. **Add authentication** - JWT-based user system
5. **Improve extraction** - Fine-tune prompts with real data

## Support

For issues:
1. Check logs in `logs/drTranscribe.log`
2. Review system design: `SYSTEM_DESIGN_MVP.md`
3. Check API status: https://status.openai.com/

## API Key Management

### Getting OpenAI API Key

1. Go to https://platform.openai.com/
2. Sign up or log in
3. Navigate to API Keys
4. Create new secret key
5. Copy and save securely (shown only once)

### API Key Security

- Never commit `.env` to git (already in .gitignore)
- Use environment variables in production
- Rotate keys regularly
- Monitor usage at https://platform.openai.com/usage

### Usage Monitoring

Check API usage:
```bash
# View logs for API calls
tail -f logs/drTranscribe.log | grep "API"
```

## Architecture Deep Dive

See `SYSTEM_DESIGN_MVP.md` for:
- Detailed architecture diagrams
- Design pattern explanations
- Provider abstraction details
- Future enhancement roadmap
- Performance optimization strategies

## Testing Checklist

- [ ] Server starts without errors
- [ ] Frontend loads at localhost:8000
- [ ] Health check returns healthy status
- [ ] Patient form accepts valid input
- [ ] Microphone permission prompt appears
- [ ] Audio recording starts successfully
- [ ] WebSocket connection establishes
- [ ] Audio chunks sent every 5 seconds
- [ ] Transcription visible in server logs
- [ ] Extraction sections update in UI
- [ ] All 5 sections populate correctly
- [ ] Stop recording ends session cleanly
- [ ] No memory leaks after multiple sessions
- [ ] Error messages display properly

## Development Tips

### Hot Reload

For development, use uvicorn with reload:
```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

### Debug Mode

Enable debug logging:
```python
# In src/main.py
logging.basicConfig(level=logging.DEBUG)
```

### Testing Audio Locally

If you don't have a microphone, you can test with:
1. Virtual audio cable (MacOS: BlackHole, Windows: VB-Cable)
2. Play audio through virtual device
3. Set browser to use virtual device

### API Response Caching

For development, cache API responses to save costs:
```python
# Add to providers (not implemented in MVP)
from functools import lru_cache
```

## File Structure Reference

```
drTranscribe/
├── src/
│   ├── main.py                      # FastAPI app, entry point
│   ├── websocket_handler.py         # WebSocket logic
│   ├── models/                      # Pydantic models
│   │   ├── patient.py               # Patient data
│   │   ├── consultation.py          # Session state
│   │   ├── extraction.py            # Extraction results
│   │   └── websocket_messages.py    # WebSocket DTOs
│   ├── services/                    # Business logic
│   │   ├── transcription_service.py # Transcription facade
│   │   ├── extraction_service.py    # Extraction facade
│   │   └── session_manager.py       # Session storage
│   ├── providers/                   # Provider implementations
│   │   ├── base.py                  # Abstract base classes
│   │   ├── transcription/
│   │   │   └── openai_whisper.py    # Whisper provider
│   │   └── extraction/
│   │       └── openai_gpt.py        # GPT-4 provider
│   └── config/
│       └── settings.py              # Config loader
├── frontend/
│   ├── index.html                   # UI structure
│   ├── app.js                       # WebSocket + audio
│   └── style.css                    # Styling
├── config/
│   └── settings.yaml                # App configuration
├── logs/                            # Application logs
├── requirements.txt                 # Python dependencies
├── Dockerfile                       # Container image
├── docker-compose.yml               # Container orchestration
└── .env.example                     # Environment template
```

## Success!

You've successfully set up drTranscribe MVP! 🎉

The system is now ready to:
- Capture real-time audio from consultations
- Transcribe with OpenAI Whisper
- Extract structured clinical data with GPT-4
- Display results live with 5-8 second latency

Start the server and try your first consultation!
