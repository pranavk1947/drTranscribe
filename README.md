# drTranscribe

Real-time medical transcription and structured clinical data extraction for doctor-patient consultations.

drTranscribe listens to medical consultations (via browser microphone or Google Meet/Zoom tab audio), transcribes speech in real-time, and uses LLMs to extract structured clinical data into five sections: **Chief Complaint**, **Diagnosis**, **Medicine**, **Advice**, and **Next Steps**.

## How It Works

```
                        Chrome Extension (Meet/Zoom)
                               |
                          Tab Audio Capture
                               |
Browser Frontend -----> WebSocket (/ws) -----> FastAPI Backend
  (Microphone)              |                       |
                            |              +--------+--------+
                            |              |                 |
                      Audio Chunks   TranscriptionService  ExtractionService
                       (WAV/16kHz)     (Speech-to-Text)    (LLM Extraction)
                                            |                 |
                                       Groq / OpenAI    Gemini / GPT-4
                                       Gemini / Azure    Claude / Groq
                                            |                 |
                                            +--------+--------+
                                                     |
                                              extraction_update
                                              (WebSocket response)
```

## Features

- **Real-time transcription** - AudioWorklet-based audio capture with 5-second WAV chunks at 16kHz mono
- **Structured clinical extraction** - LLM-powered extraction into 5 standardized medical sections
- **Chrome Extension** - Captures tab audio from Google Meet and Zoom calls directly
- **Multi-provider support** - Swap transcription and extraction providers via config (no code changes)
- **Pause/Resume** - Pause recording mid-consultation without losing context
- **Export to EMR** - Generate PDF exports of extracted clinical data
- **Low latency** - End-to-end pipeline runs in 5-8 seconds

## Provider Matrix

| Provider | Transcription | Extraction | Notes |
|----------|:---:|:---:|-------|
| **Groq** | Default | Supported | Free tier available, fastest transcription |
| **Google Gemini** | Supported | Default | Gemini 2.5 Flash for extraction |
| **OpenAI** | Supported | Supported | Whisper + GPT-4 |
| **Azure OpenAI** | Supported | Supported | Enterprise deployments |
| **Anthropic Claude** | - | Supported | Claude for extraction only |
| **Mock** | Supported | Supported | For development/testing without API keys |

## Quick Start

### Prerequisites

- Python 3.11+
- At least one API key (Groq recommended for free tier)
- Chrome browser (for the extension)

### 1. Clone and install

```bash
git clone https://github.com/pranavk1947/drTranscribe.git
cd drTranscribe
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and add your API keys (only the providers you plan to use)
```

### 3. Run the server

```bash
python -m src.main
```

The server starts at `http://localhost:8000`. Open it in your browser to use the web frontend directly with your microphone.

### 4. Install the Chrome Extension (optional)

For capturing audio from Google Meet or Zoom calls:

1. Download the latest extension zip from the [Releases page](https://github.com/pranavk1947/drTranscribe/releases) or use the `dist/drTranscribe-extension.zip` in this repo
2. Unzip to a local folder
3. Open `chrome://extensions/` in Chrome
4. Enable **Developer mode** (top right toggle)
5. Click **Load unpacked** and select the unzipped folder
6. Click the extension icon to configure your server URL (default: `http://localhost:8080`)

### Docker

```bash
cp .env.example .env
# Edit .env with your API keys

docker-compose up -d
curl http://localhost:8000/health
```

## Configuration

Edit `config/settings.yaml` to switch providers:

```yaml
transcription:
  provider: "groq"       # Options: groq, gemini, openai, azure, google_stt, mock
  model: "whisper-large-v3"

extraction:
  provider: "gemini"     # Options: gemini, openai, azure, claude, groq, mock
  model: "gemini-2.5-flash"
  temperature: 0.3

audio:
  chunk_duration_seconds: 5
  sample_rate: 16000
  channels: 1
```

## Project Structure

```
drTranscribe/
├── src/                          # FastAPI backend
│   ├── main.py                   # Application entry point
│   ├── websocket_handler.py      # WebSocket connection handler
│   ├── config/
│   │   └── settings.py           # Pydantic config loader
│   ├── services/
│   │   ├── transcription_service.py
│   │   ├── extraction_service.py
│   │   ├── session_manager.py
│   │   └── audio_storage.py
│   ├── providers/
│   │   ├── transcription/        # Speech-to-text providers
│   │   │   ├── groq_whisper.py
│   │   │   ├── openai_whisper.py
│   │   │   ├── gemini_stt.py
│   │   │   ├── google_stt.py
│   │   │   ├── azure_whisper.py
│   │   │   └── mock_whisper.py
│   │   └── extraction/           # LLM extraction providers
│   │       ├── gemini_gpt.py
│   │       ├── openai_gpt.py
│   │       ├── azure_gpt.py
│   │       ├── claude_gpt.py
│   │       ├── groq_gpt.py
│   │       ├── mock_gpt.py
│   │       └── prompts.py
│   └── models/
│       ├── patient.py
│       ├── consultation.py
│       ├── extraction.py
│       └── websocket_messages.py
├── frontend/                     # Web UI (vanilla JS)
│   ├── index.html
│   ├── app.js
│   ├── audio-recorder.js
│   ├── audio-worklet-processor.js
│   ├── wav-encoder.js
│   └── style.css
├── chromeExtension/              # Chrome Extension (Manifest V3)
│   ├── manifest.json
│   ├── background.js             # Service worker (WebSocket + tab capture)
│   ├── content.js                # Injected overlay for Meet/Zoom
│   ├── offscreen.js              # Audio capture via offscreen document
│   ├── popup.html/js/css         # Extension popup (settings)
│   ├── export.js                 # PDF export for EMR
│   └── icons/
├── config/
│   └── settings.yaml             # Runtime configuration
├── dist/
│   └── drTranscribe-extension.zip  # Pre-built extension for download
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

## WebSocket Protocol

### Client to Server

**Start Session:**
```json
{ "type": "start_session", "appointment_id": "apt-123" }
```

**Audio Chunk:**
```json
{ "type": "audio_chunk", "audio_data": "<base64-wav>", "source": "mic" }
```

**Pause / Resume:**
```json
{ "type": "pause_session", "appointment_id": "apt-123" }
{ "type": "session_resume", "appointment_id": "apt-123" }
```

**Stop Session:**
```json
{ "type": "stop_session", "appointment_id": "apt-123" }
```

### Server to Client

**Extraction Update:**
```json
{
  "type": "extraction_update",
  "extraction": {
    "chief_complaint": "Patient presents with...",
    "diagnosis": "...",
    "medicine": "...",
    "advice": "...",
    "next_steps": "..."
  }
}
```

**Transcription Update:**
```json
{ "type": "transcription_update", "text": "...", "source": "mic" }
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Serve web frontend |
| `GET` | `/health` | Health check |
| `GET` | `/api/config` | Audio configuration for clients |
| `WS` | `/ws` | WebSocket for real-time transcription |

## Architecture

- **Strategy Pattern** - Provider abstraction allows swapping transcription/extraction backends via config
- **Factory Pattern** - Provider instantiation based on `settings.yaml`
- **AudioWorklet** - Separate audio thread for zero-drop capture
- **Offscreen Document** - Chrome Extension uses offscreen API for tab audio capture (Manifest V3)
- **WebSocket** - Bidirectional real-time communication between all clients and the backend

## Development

```bash
# Run with mock providers (no API keys needed)
# Set in config/settings.yaml:
#   transcription.provider: "mock"
#   extraction.provider: "mock"
python -m src.main

# Run tests
pytest tests/
```

## License

MIT License - see [LICENSE](LICENSE) for details.
