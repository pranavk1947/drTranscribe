# MedLog

Real-time medical transcription system with structured clinical data extraction.

## Features

- **Real-time Audio Capture**: AudioWorklet-based medical-grade audio capture with configurable chunking (WAV format, 16kHz, mono)
- **Automatic Transcription**: Groq Whisper API for fast, accurate speech-to-text
- **Structured Extraction**: GPT-4 powered extraction of clinical data into 5 sections:
  - Chief Complaint
  - Diagnosis
  - Medicine
  - Advice
  - Next Steps
- **Live Updates**: Real-time display of extracted information (5-8 second latency)
- **Provider Abstraction**: Configuration-based switching between providers
- **No Persistence**: MVP scope - data discarded after session

## Audio Technology

**AudioWorklet + WAV Encoding**

MedLog uses modern Web Audio API with AudioWorklet for medical-grade audio capture:

- ✅ **Complete WAV files**: Each chunk is a valid, standalone audio file
- ✅ **Groq-optimized**: 16kHz mono WAV (Groq's recommended format)
- ✅ **Real-time**: Configurable 5-second chunks for immediate transcription
- ✅ **Medical-grade**: No audio drops, no fragmentation, complete data capture
- ✅ **Performance**: Runs on separate audio thread with zero-copy transfer

**Browser Requirements:**
- Chrome 66+ ✅
- Firefox 76+ ✅
- Safari 14.1+ ✅
- Edge 79+ ✅

**Configuration:**
Audio settings in `config/settings.yaml`:
- `chunk_duration_seconds`: Duration of each audio chunk (default: 5)
- `sample_rate`: Audio sample rate in Hz (default: 16000)
- `channels`: Number of channels (default: 1 = mono)

## Architecture

```
Frontend (HTML/CSS/JS)
  ↓ WebSocket
Backend (FastAPI)
  ├→ TranscriptionService (OpenAI Whisper)
  └→ ExtractionService (OpenAI GPT-4)
```

**Design Patterns:**
- Strategy Pattern for provider abstraction
- Factory Pattern for provider instantiation
- Dependency Injection for loose coupling

## Quick Start

### Prerequisites

- Python 3.11+
- OpenAI API key
- Modern web browser with microphone access

### Installation

1. Clone the repository
2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure environment:
```bash
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY
```

4. Run the application:
```bash
python -m src.main
```

5. Open browser to `http://localhost:8000`

### Docker Deployment

```bash
# Set environment variable
export OPENAI_API_KEY=your_key_here

# Run with Docker Compose
docker-compose up -d

# Check health
curl http://localhost:8000/health
```

## Usage

1. Enter patient information (name, age, gender)
2. Click "Start Recording" and grant microphone permission
3. Conduct the consultation normally
4. Watch extraction sections update in real-time
5. Click "Stop Recording" to end session

## Configuration

Edit `config/settings.yaml` to switch providers:

```yaml
transcription:
  provider: "openai"  # Change to "groq" when implemented
  model: "whisper-1"

extraction:
  provider: "openai"  # Change to "groq" when implemented
  model: "gpt-4"
  temperature: 0.3
```

## Project Structure

```
MedLog/
├── src/
│   ├── main.py                  # FastAPI application
│   ├── websocket_handler.py     # WebSocket connection handler
│   ├── services/
│   │   ├── transcription_service.py
│   │   ├── extraction_service.py
│   │   └── session_manager.py
│   ├── providers/
│   │   ├── base.py              # Abstract base classes
│   │   ├── transcription/
│   │   │   └── openai_whisper.py
│   │   └── extraction/
│   │       └── openai_gpt.py
│   ├── models/
│   │   ├── patient.py
│   │   ├── consultation.py
│   │   ├── extraction.py
│   │   └── websocket_messages.py
│   └── config/
│       └── settings.py
├── frontend/
│   ├── index.html
│   ├── app.js
│   └── style.css
├── config/
│   └── settings.yaml
├── logs/
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

## API Endpoints

- `GET /` - Serve frontend
- `GET /health` - Health check
- `WebSocket /ws` - Real-time transcription

## WebSocket Protocol

### Client → Server

**Start Session:**
```json
{
  "type": "start_session",
  "patient": {
    "name": "John Doe",
    "age": 45,
    "gender": "Male"
  }
}
```

**Audio Chunk:**
```json
{
  "type": "audio_chunk",
  "audio_data": "base64_encoded_audio"
}
```

**Stop Session:**
```json
{
  "type": "stop_session"
}
```

### Server → Client

**Extraction Update:**
```json
{
  "type": "extraction_update",
  "extraction": {
    "chief_complaint": "...",
    "diagnosis": "...",
    "medicine": "...",
    "advice": "...",
    "next_steps": "..."
  }
}
```

**Error:**
```json
{
  "type": "error",
  "message": "Error description"
}
```

## Cost Estimates

**MVP (OpenAI):**
- 1000 consultations/month (avg 10 min)
- Transcription: $60/month
- Extraction: $55/month
- **Total: $115/month**

## Future Enhancements

- Add Groq providers (5x faster, 10x cheaper)
- PostgreSQL persistence
- Multi-user authentication
- Real-time transcript display
- Speaker diarization
- Mobile app

## License

Proprietary - All rights reserved

## Support

For issues and feature requests, contact the development team.
