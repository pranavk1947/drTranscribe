# drTranscribe MVP - System Design Document

**Version:** 1.0.0
**Date:** 2026-02-05
**Status:** Draft
**Author:** Technical Team

---

## Executive Summary

**drTranscribe MVP** is a real-time medical transcription system designed to assist doctors during patient consultations. The system captures audio from doctor-patient conversations, transcribes them using OpenAI Whisper, and automatically extracts structured clinical information (chief complaint, diagnosis, medicine, advice, next steps) using GPT-4.

**Key Features:**
- Real-time audio capture via browser microphone
- Near real-time extraction (5-8 second latency)
- Structured clinical data in 5 sections
- Configuration-based model switching for future flexibility
- Simple HTML/CSS frontend with start/stop controls
- No data persistence (MVP scope)
- Local deployment with Docker

**Target Users:** Medical practitioners conducting patient consultations

**Technology:** FastAPI backend, WebSocket communication, OpenAI APIs, HTML/CSS/JS frontend

**Timeline:** MVP deliverable for development team

---

## System Architecture

### Overview

drTranscribe MVP is a real-time medical transcription system that captures doctor-patient conversations, transcribes them using OpenAI Whisper, and extracts structured clinical information using GPT-4. The system processes audio in 5-second chunks to provide near real-time updates with acceptable 5-8 second latency.

### High-Level Components

```
┌─────────────────────────────────────────────────────────────────┐
│                         FRONTEND (HTML/CSS/JS)                  │
│                                                                 │
│  ┌──────────────┐  ┌─────────────────────────────────────┐   │
│  │ Patient Info │  │  Audio Capture (Browser Microphone)  │   │
│  │ - Name       │  │  - Start Recording Button            │   │
│  │ - Age        │  │  - Stop Recording Button             │   │
│  │ - Gender     │  │  - 5-second Audio Buffer             │   │
│  └──────────────┘  └─────────────────────────────────────┘   │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │          Real-Time Extraction Display                    │ │
│  │  • Chief Complaint                                       │ │
│  │  • Diagnosis                                             │ │
│  │  • Medicine                                              │ │
│  │  • Advice                                                │ │
│  │  • Next-Steps (Lab/Follow-up/Cross-consultation)        │ │
│  └──────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ WebSocket Connection
                              │ (Audio chunks + Patient metadata)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    BACKEND (FastAPI + WebSocket)                │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │          WebSocket Handler                              │  │
│  │  - Receive audio chunks (5-second buffers)              │  │
│  │  - Maintain session state                               │  │
│  │  - Send extraction updates to frontend                  │  │
│  └─────────────────────────────────────────────────────────┘  │
│                              │                                  │
│                              ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │     Audio Processing Pipeline                           │  │
│  │  1. Receive 5-second audio chunk                        │  │
│  │  2. Send to Transcription Service                       │  │
│  │  3. Get transcript text                                 │  │
│  │  4. Send transcript to Extraction Service               │  │
│  │  5. Get structured data                                 │  │
│  │  6. Emit update via WebSocket                           │  │
│  └─────────────────────────────────────────────────────────┘  │
│                              │                                  │
│                    ┌─────────┴─────────┐                       │
│                    │                   │                       │
│                    ▼                   ▼                       │
│  ┌───────────────────────────┐  ┌──────────────────────────┐  │
│  │  Transcription Service    │  │  Extraction Service      │  │
│  │  - Provider abstraction   │  │  - Provider abstraction  │  │
│  │  - Config-based switching │  │  - Config-based model    │  │
│  │  - OpenAI Whisper (MVP)   │  │  - OpenAI GPT-4 (MVP)    │  │
│  └───────────────────────────┘  └──────────────────────────┘  │
│                    │                   │                       │
└────────────────────┼───────────────────┼───────────────────────┘
                     │                   │
                     └─────────┬─────────┘
                               │ HTTPS API Calls
                               ▼
                   ┌──────────────────────────┐
                   │   OpenAI API Services    │
                   │  - Whisper API           │
                   │  - GPT-4 API             │
                   └──────────────────────────┘
```

### Data Flow: Audio Processing Pipeline

```
┌──────────────────────────────────────────────────────────────────────┐
│                     COMPLETE DATA FLOW                               │
└──────────────────────────────────────────────────────────────────────┘

1. User clicks "Start Recording"
         │
         ▼
2. Frontend collects patient metadata (name, age, gender)
         │
         ▼
3. WebSocket connection established
         │
         ▼
4. Browser captures audio from microphone
         │
         ├─→ Audio buffered in 5-second chunks
         │
         ▼
5. Every 5 seconds: Send audio chunk to backend via WebSocket
         │
         ▼
6. Backend receives audio chunk
         │
         ├─→ TranscriptionService.transcribe(audio_chunk)
         │         │
         │         ├─→ Read config: transcription.provider = "openai"
         │         │
         │         ├─→ OpenAIWhisperProvider.transcribe(audio_chunk)
         │         │         │
         │         │         └─→ POST https://api.openai.com/v1/audio/transcriptions
         │         │                   Body: audio file + model="whisper-1"
         │         │                   Response: {"text": "Patient says..."}
         │         │
         │         └─→ Return transcript text
         │
         ▼
7. Backend receives transcript: "Patient says I have a headache for 3 days"
         │
         ├─→ ExtractionService.extract(transcript, patient_context)
         │         │
         │         ├─→ Read config: extraction.provider = "openai"
         │         │
         │         ├─→ OpenAIGPTProvider.extract(transcript)
         │         │         │
         │         │         ├─→ Build prompt with extraction schema
         │         │         │
         │         │         ├─→ POST https://api.openai.com/v1/chat/completions
         │         │         │     Body: {
         │         │         │       model: "gpt-4",
         │         │         │       messages: [system_prompt, user_transcript]
         │         │         │     }
         │         │         │     Response: {
         │         │         │       "chief_complaint": "Headache for 3 days",
         │         │         │       "diagnosis": "",
         │         │         │       "medicine": "",
         │         │         │       "advice": "",
         │         │         │       "next_steps": ""
         │         │         │     }
         │         │         │
         │         │         └─→ Return structured extraction
         │         │
         │         └─→ Merge with existing session state
         │
         ▼
8. Backend sends update via WebSocket to frontend
         │
         ▼
9. Frontend updates UI in real-time
         │
         ├─→ Chief Complaint: "Headache for 3 days"
         ├─→ Diagnosis: (empty, waiting for more conversation)
         └─→ Other sections: (empty)
         │
         ▼
10. Loop continues every 5 seconds until "Stop Recording"
         │
         ▼
11. User clicks "Stop Recording"
         │
         ├─→ WebSocket closed
         └─→ Session data discarded (no persistence for MVP)
```

### Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Frontend** | HTML5/CSS3/JavaScript | Simple UI with audio capture |
| **Audio API** | MediaRecorder API | Browser microphone access |
| **WebSocket** | WebSocket API (Browser) | Real-time bidirectional communication |
| **Backend Framework** | FastAPI 0.115+ | Async Python web framework |
| **WebSocket Server** | Uvicorn with WebSocket support | ASGI server for WebSocket |
| **Transcription** | OpenAI Whisper API | Speech-to-text conversion |
| **Extraction** | OpenAI GPT-4 | Structured clinical data extraction |
| **Configuration** | YAML/TOML config file | Model provider switching |
| **Deployment** | Docker + Docker Compose | Containerized local deployment |

### Component Responsibilities

#### Frontend (HTML/CSS/JS)
- Collect patient metadata (name, age, gender)
- Capture audio from browser microphone
- Buffer audio in 5-second chunks
- Establish WebSocket connection to backend
- Send audio chunks via WebSocket
- Receive extraction updates
- Display structured data in real-time
- Handle start/stop recording controls

#### Backend (FastAPI)
- Accept WebSocket connections
- Receive audio chunks from frontend
- Maintain session state per connection
- Route audio to TranscriptionService
- Route transcript to ExtractionService
- Merge incremental extractions
- Send updates to frontend via WebSocket
- Load configuration for model providers

#### TranscriptionService
- Abstract interface for transcription providers
- Load provider from configuration
- Convert audio bytes to text
- Handle API errors and retries
- OpenAI Whisper implementation (MVP)

#### ExtractionService
- Abstract interface for extraction providers
- Load provider from configuration
- Extract structured clinical data from transcript
- Merge with existing session data
- Handle API errors and retries
- OpenAI GPT-4 implementation (MVP)

### Configuration-Based Model Switching

```yaml
# config/settings.yaml

transcription:
  provider: "openai"  # Options: "openai", "groq", "deepgram"
  model: "whisper-1"

extraction:
  provider: "openai"  # Options: "openai", "groq", "anthropic"
  model: "gpt-4"
  temperature: 0.3

openai:
  api_key: "${OPENAI_API_KEY}"

# Future providers (not implemented in MVP)
groq:
  api_key: "${GROQ_API_KEY}"

deepgram:
  api_key: "${DEEPGRAM_API_KEY}"
```

**Design Pattern**: Strategy Pattern with Provider Abstraction

```python
# Example provider interface
class TranscriptionProvider(ABC):
    @abstractmethod
    def transcribe(self, audio_bytes: bytes) -> str:
        pass

class OpenAIWhisperProvider(TranscriptionProvider):
    def transcribe(self, audio_bytes: bytes) -> str:
        # OpenAI Whisper API call
        pass

class GroqWhisperProvider(TranscriptionProvider):
    def transcribe(self, audio_bytes: bytes) -> str:
        # Groq Whisper API call
        pass

# Factory loads provider from config
provider = TranscriptionProviderFactory.create(config.transcription.provider)
transcript = provider.transcribe(audio)
```

### Session State Management

```
Session Lifecycle:
  1. WebSocket connection opened
       → Create new ConsultationSession(patient_info)
       → Initialize empty extraction data

  2. Audio chunks received
       → Transcribe → Extract → Merge into session
       → session.chief_complaint += new_complaint
       → session.diagnosis += new_diagnosis
       (Incremental updates, not replacement)

  3. WebSocket connection closed
       → Discard session (no persistence for MVP)
       → Free memory
```

### Communication Protocols

**WebSocket Messages (Frontend → Backend)**
```json
{
  "type": "start_session",
  "patient": {
    "name": "John Doe",
    "age": 45,
    "gender": "Male"
  }
}

{
  "type": "audio_chunk",
  "audio": "<base64_encoded_audio>",
  "chunk_number": 1,
  "timestamp": "2026-02-05T10:30:05Z"
}

{
  "type": "stop_session"
}
```

**WebSocket Messages (Backend → Frontend)**
```json
{
  "type": "extraction_update",
  "data": {
    "chief_complaint": "Headache for 3 days, worsening",
    "diagnosis": "Migraine (tentative)",
    "medicine": "Ibuprofen 400mg",
    "advice": "Rest in dark room, avoid screens",
    "next_steps": "Follow-up: If no improvement in 48 hours"
  },
  "chunk_number": 3,
  "timestamp": "2026-02-05T10:30:15Z"
}

{
  "type": "error",
  "message": "Transcription failed: OpenAI API timeout",
  "recoverable": true
}
```

### System Constraints (MVP Scope)

**In Scope:**
- Single concurrent consultation session
- Browser-based audio capture
- 5-8 second latency for extraction updates
- Configuration-based model switching
- Local deployment (Docker)
- Basic error handling

**Out of Scope (Future Enhancements):**
- Multiple concurrent sessions
- Data persistence (database)
- User authentication
- Patient history integration
- Advanced audio preprocessing (noise reduction)
- Cloud deployment (GCP/AWS)
- Real-time transcript display
- Audio recording save/replay

---

## Frontend Design

### UI Layout

```
┌─────────────────────────────────────────────────────────────┐
│                     drTranscribe MVP                        │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  Patient Information                                        │
│  ┌──────────────┐  ┌──────────┐  ┌─────────────┐         │
│  │ Name: [____] │  │ Age: [__]│  │ Gender: [▼] │         │
│  └──────────────┘  └──────────┘  └─────────────┘         │
│                                                             │
│  [🎤 Start Recording]  [⏹️ Stop Recording (disabled)]      │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  Chief Complaint                                            │
│  ┌───────────────────────────────────────────────────────┐ │
│  │ (Updates in real-time as conversation progresses)     │ │
│  │                                                        │ │
│  └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  Diagnosis                                                  │
│  ┌───────────────────────────────────────────────────────┐ │
│  │ (Updates in real-time)                                │ │
│  └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  Medicine                                                   │
│  ┌───────────────────────────────────────────────────────┐ │
│  │ (Updates in real-time)                                │ │
│  └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  Advice                                                     │
│  ┌───────────────────────────────────────────────────────┐ │
│  │ (Updates in real-time)                                │ │
│  └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  Next Steps                                                 │
│  ┌───────────────────────────────────────────────────────┐ │
│  │ Lab Tests: (updates in real-time)                     │ │
│  │ Follow-up: (updates in real-time)                     │ │
│  │ Cross-consultation: (updates in real-time)            │ │
│  └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### User Flow

1. **Page Load**
   - Display patient information form
   - Start Recording button enabled
   - Stop Recording button disabled
   - All extraction sections empty

2. **Start Recording**
   - User fills patient info (name, age, gender)
   - User clicks "Start Recording"
   - Request microphone permission (if not granted)
   - Establish WebSocket connection to backend
   - Send patient metadata via WebSocket
   - Enable Stop Recording button
   - Disable Start Recording button
   - Start capturing audio from microphone
   - Buffer audio in 5-second chunks
   - Send each chunk to backend

3. **During Recording**
   - Every 5 seconds: send audio chunk
   - Receive extraction updates from backend
   - Update corresponding sections in UI
   - Append new information (don't replace)

4. **Stop Recording**
   - User clicks "Stop Recording"
   - Stop audio capture
   - Close WebSocket connection
   - Disable Stop Recording button
   - Keep extracted data visible on screen
   - Data is lost when page is refreshed (no persistence)

### Technology Implementation

**HTML Structure:**
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>drTranscribe MVP</title>
    <link rel="stylesheet" href="style.css">
</head>
<body>
    <div class="container">
        <h1>drTranscribe MVP</h1>

        <!-- Patient Info Form -->
        <div class="patient-info">
            <input type="text" id="patientName" placeholder="Patient Name" required>
            <input type="number" id="patientAge" placeholder="Age" required>
            <select id="patientGender">
                <option value="">Select Gender</option>
                <option value="Male">Male</option>
                <option value="Female">Female</option>
                <option value="Other">Other</option>
            </select>
        </div>

        <!-- Recording Controls -->
        <div class="controls">
            <button id="startBtn">🎤 Start Recording</button>
            <button id="stopBtn" disabled>⏹️ Stop Recording</button>
        </div>

        <!-- Extraction Sections -->
        <div class="section">
            <h2>Chief Complaint</h2>
            <div id="chiefComplaint" class="content"></div>
        </div>

        <div class="section">
            <h2>Diagnosis</h2>
            <div id="diagnosis" class="content"></div>
        </div>

        <div class="section">
            <h2>Medicine</h2>
            <div id="medicine" class="content"></div>
        </div>

        <div class="section">
            <h2>Advice</h2>
            <div id="advice" class="content"></div>
        </div>

        <div class="section">
            <h2>Next Steps</h2>
            <div id="nextSteps" class="content"></div>
        </div>
    </div>

    <script src="app.js"></script>
</body>
</html>
```

**JavaScript Audio Capture & WebSocket:**
```javascript
// app.js
let mediaRecorder;
let audioChunks = [];
let websocket;
let chunkNumber = 0;

// WebSocket connection
function connectWebSocket() {
    websocket = new WebSocket('ws://localhost:8000/ws');

    websocket.onopen = () => {
        console.log('WebSocket connected');
        sendPatientInfo();
    };

    websocket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        updateExtractionUI(data);
    };

    websocket.onerror = (error) => {
        console.error('WebSocket error:', error);
        alert('Connection error. Please try again.');
    };
}

// Send patient metadata
function sendPatientInfo() {
    const patientInfo = {
        type: 'start_session',
        patient: {
            name: document.getElementById('patientName').value,
            age: parseInt(document.getElementById('patientAge').value),
            gender: document.getElementById('patientGender').value
        }
    };
    websocket.send(JSON.stringify(patientInfo));
}

// Start recording
async function startRecording() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

        // MediaRecorder with 5-second chunks
        mediaRecorder = new MediaRecorder(stream);
        mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0) {
                sendAudioChunk(event.data);
            }
        };

        // Emit data every 5 seconds
        mediaRecorder.start(5000); // timeslice = 5000ms

        // Connect WebSocket
        connectWebSocket();

        // Update UI
        document.getElementById('startBtn').disabled = true;
        document.getElementById('stopBtn').disabled = false;

    } catch (error) {
        console.error('Error accessing microphone:', error);
        alert('Could not access microphone. Please grant permission.');
    }
}

// Stop recording
function stopRecording() {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
        mediaRecorder.stop();
        mediaRecorder.stream.getTracks().forEach(track => track.stop());
    }

    if (websocket) {
        websocket.send(JSON.stringify({ type: 'stop_session' }));
        websocket.close();
    }

    // Update UI
    document.getElementById('startBtn').disabled = false;
    document.getElementById('stopBtn').disabled = true;
}

// Send audio chunk to backend
function sendAudioChunk(audioBlob) {
    const reader = new FileReader();
    reader.onloadend = () => {
        const base64Audio = reader.result.split(',')[1];
        const message = {
            type: 'audio_chunk',
            audio: base64Audio,
            chunk_number: chunkNumber++,
            timestamp: new Date().toISOString()
        };
        websocket.send(JSON.stringify(message));
    };
    reader.readAsDataURL(audioBlob);
}

// Update UI with extraction results
function updateExtractionUI(data) {
    if (data.type === 'extraction_update') {
        document.getElementById('chiefComplaint').textContent = data.data.chief_complaint || '';
        document.getElementById('diagnosis').textContent = data.data.diagnosis || '';
        document.getElementById('medicine').textContent = data.data.medicine || '';
        document.getElementById('advice').textContent = data.data.advice || '';
        document.getElementById('nextSteps').textContent = data.data.next_steps || '';
    } else if (data.type === 'error') {
        console.error('Backend error:', data.message);
        alert('Processing error: ' + data.message);
    }
}

// Event listeners
document.getElementById('startBtn').addEventListener('click', startRecording);
document.getElementById('stopBtn').addEventListener('click', stopRecording);
```

**CSS Styling:**
```css
/* style.css */
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    background-color: #f5f5f5;
    padding: 20px;
}

.container {
    max-width: 900px;
    margin: 0 auto;
    background: white;
    padding: 30px;
    border-radius: 8px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
}

h1 {
    text-align: center;
    color: #2c3e50;
    margin-bottom: 30px;
}

.patient-info {
    display: flex;
    gap: 15px;
    margin-bottom: 20px;
}

.patient-info input,
.patient-info select {
    flex: 1;
    padding: 12px;
    border: 1px solid #ddd;
    border-radius: 4px;
    font-size: 14px;
}

.controls {
    display: flex;
    gap: 15px;
    margin-bottom: 30px;
    justify-content: center;
}

button {
    padding: 12px 30px;
    font-size: 16px;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    transition: background-color 0.3s;
}

#startBtn {
    background-color: #27ae60;
    color: white;
}

#startBtn:hover:not(:disabled) {
    background-color: #229954;
}

#stopBtn {
    background-color: #e74c3c;
    color: white;
}

#stopBtn:hover:not(:disabled) {
    background-color: #c0392b;
}

button:disabled {
    background-color: #95a5a6;
    cursor: not-allowed;
    opacity: 0.6;
}

.section {
    margin-bottom: 25px;
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    padding: 15px;
}

.section h2 {
    color: #34495e;
    font-size: 18px;
    margin-bottom: 10px;
    border-bottom: 2px solid #3498db;
    padding-bottom: 5px;
}

.content {
    min-height: 60px;
    padding: 10px;
    background-color: #f9f9f9;
    border-radius: 4px;
    white-space: pre-wrap;
    line-height: 1.6;
    color: #2c3e50;
}

.content:empty::before {
    content: 'Waiting for audio...';
    color: #95a5a6;
    font-style: italic;
}
```

### Browser Requirements

- **Modern Browser**: Chrome 60+, Firefox 55+, Safari 14+, Edge 79+
- **HTTPS Required**: MediaRecorder API requires secure context (localhost is exempt)
- **Microphone Permission**: User must grant microphone access
- **WebSocket Support**: All modern browsers support WebSocket

---

## Backend Design

### Project Structure

```
drTranscribe/
├── src/
│   ├── main.py                    # FastAPI app entry point
│   ├── websocket_handler.py       # WebSocket connection handler
│   ├── services/
│   │   ├── __init__.py
│   │   ├── transcription_service.py    # Transcription abstraction
│   │   ├── extraction_service.py       # Extraction abstraction
│   │   └── session_manager.py          # Session state management
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py                     # Abstract base classes
│   │   ├── transcription/
│   │   │   ├── __init__.py
│   │   │   └── openai_whisper.py       # OpenAI Whisper implementation
│   │   └── extraction/
│   │       ├── __init__.py
│   │       └── openai_gpt.py           # OpenAI GPT-4 implementation
│   ├── models/
│   │   ├── __init__.py
│   │   ├── patient.py                  # Patient data model
│   │   ├── consultation.py             # Consultation session model
│   │   └── extraction.py               # Extraction result model
│   └── config/
│       ├── __init__.py
│       └── settings.py                 # Configuration management
├── config/
│   └── settings.yaml                   # Configuration file
├── frontend/
│   ├── index.html
│   ├── app.js
│   └── style.css
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

### Core Components

#### 1. FastAPI Application (main.py)

```python
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import logging

from src.websocket_handler import WebSocketHandler
from src.config.settings import load_config

# Initialize FastAPI app
app = FastAPI(
    title="drTranscribe MVP",
    description="Real-time medical transcription with structured extraction",
    version="1.0.0"
)

# Load configuration
config = load_config()

# Initialize WebSocket handler
ws_handler = WebSocketHandler(config)

# Serve frontend static files
app.mount("/static", StaticFiles(directory="frontend"), name="static")

@app.get("/")
async def root():
    """Serve frontend HTML"""
    with open("frontend/index.html") as f:
        return HTMLResponse(content=f.read())

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time audio processing
    """
    await websocket.accept()
    try:
        await ws_handler.handle_connection(websocket)
    except WebSocketDisconnect:
        logging.info("Client disconnected")
    except Exception as e:
        logging.error(f"WebSocket error: {e}")
        await websocket.close(code=1011, reason=str(e))

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "drTranscribe MVP"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

#### 2. WebSocket Handler (websocket_handler.py)

```python
from fastapi import WebSocket
import json
import base64
import logging
from typing import Optional

from src.services.transcription_service import TranscriptionService
from src.services.extraction_service import ExtractionService
from src.services.session_manager import SessionManager
from src.models.patient import Patient
from src.models.consultation import ConsultationSession

class WebSocketHandler:
    """
    Handles WebSocket connections and orchestrates audio processing pipeline
    """

    def __init__(self, config):
        self.config = config
        self.transcription_service = TranscriptionService(config)
        self.extraction_service = ExtractionService(config)
        self.session_manager = SessionManager()
        self.logger = logging.getLogger(__name__)

    async def handle_connection(self, websocket: WebSocket):
        """
        Main WebSocket connection handler

        Flow:
        1. Receive start_session message with patient info
        2. Create session
        3. Receive audio chunks
        4. Process each chunk (transcribe → extract → send update)
        5. Handle stop_session message
        """
        session: Optional[ConsultationSession] = None

        while True:
            # Receive message from frontend
            data = await websocket.receive_text()
            message = json.loads(data)

            msg_type = message.get("type")

            if msg_type == "start_session":
                # Create new session
                patient_data = message.get("patient")
                patient = Patient(**patient_data)
                session = self.session_manager.create_session(patient)
                self.logger.info(f"Session started for patient: {patient.name}")

                await websocket.send_json({
                    "type": "session_started",
                    "session_id": session.session_id
                })

            elif msg_type == "audio_chunk":
                if not session:
                    await websocket.send_json({
                        "type": "error",
                        "message": "No active session. Send start_session first."
                    })
                    continue

                # Decode audio from base64
                audio_base64 = message.get("audio")
                audio_bytes = base64.b64decode(audio_base64)

                # Process audio chunk
                try:
                    extraction_result = await self.process_audio_chunk(
                        session, audio_bytes
                    )

                    # Send extraction update to frontend
                    await websocket.send_json({
                        "type": "extraction_update",
                        "data": extraction_result.dict(),
                        "chunk_number": message.get("chunk_number"),
                        "timestamp": message.get("timestamp")
                    })

                except Exception as e:
                    self.logger.error(f"Error processing audio chunk: {e}")
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Processing failed: {str(e)}",
                        "recoverable": True
                    })

            elif msg_type == "stop_session":
                if session:
                    self.session_manager.end_session(session.session_id)
                    self.logger.info(f"Session ended: {session.session_id}")

                await websocket.send_json({
                    "type": "session_ended"
                })
                break

            else:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Unknown message type: {msg_type}"
                })

    async def process_audio_chunk(
        self,
        session: ConsultationSession,
        audio_bytes: bytes
    ):
        """
        Process single audio chunk through the pipeline

        Steps:
        1. Transcribe audio → text
        2. Extract structured data from text
        3. Merge with existing session data
        4. Return updated extraction
        """
        # Step 1: Transcribe
        transcript = await self.transcription_service.transcribe(audio_bytes)
        self.logger.info(f"Transcribed: {transcript[:50]}...")

        # Step 2: Extract structured data
        extraction = await self.extraction_service.extract(
            transcript=transcript,
            patient=session.patient,
            previous_extraction=session.extraction
        )

        # Step 3: Merge with session
        session.add_transcript_chunk(transcript)
        session.update_extraction(extraction)

        return session.extraction
```

#### 3. Transcription Service (services/transcription_service.py)

```python
import logging
from src.config.settings import Config
from src.providers.base import TranscriptionProvider
from src.providers.transcription.openai_whisper import OpenAIWhisperProvider

class TranscriptionService:
    """
    Transcription service with provider abstraction

    Responsibilities:
    - Load provider from configuration
    - Route transcription requests to provider
    - Handle errors and retries
    """

    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.provider = self._load_provider()

    def _load_provider(self) -> TranscriptionProvider:
        """
        Load transcription provider from config

        Strategy Pattern: Provider selected at runtime based on config
        """
        provider_name = self.config.transcription.provider

        if provider_name == "openai":
            return OpenAIWhisperProvider(self.config)
        # elif provider_name == "groq":
        #     return GroqWhisperProvider(self.config)
        # elif provider_name == "deepgram":
        #     return DeepgramProvider(self.config)
        else:
            raise ValueError(f"Unknown transcription provider: {provider_name}")

    async def transcribe(self, audio_bytes: bytes) -> str:
        """
        Transcribe audio bytes to text

        Args:
            audio_bytes: Raw audio data

        Returns:
            Transcribed text
        """
        try:
            transcript = await self.provider.transcribe(audio_bytes)
            return transcript
        except Exception as e:
            self.logger.error(f"Transcription failed: {e}")
            raise
```

#### 4. Extraction Service (services/extraction_service.py)

```python
import logging
from typing import Optional
from src.config.settings import Config
from src.providers.base import ExtractionProvider
from src.providers.extraction.openai_gpt import OpenAIGPTProvider
from src.models.patient import Patient
from src.models.extraction import ExtractionResult

class ExtractionService:
    """
    Structured extraction service with provider abstraction

    Responsibilities:
    - Load provider from configuration
    - Route extraction requests to provider
    - Merge incremental extractions
    """

    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.provider = self._load_provider()

    def _load_provider(self) -> ExtractionProvider:
        """Load extraction provider from config"""
        provider_name = self.config.extraction.provider

        if provider_name == "openai":
            return OpenAIGPTProvider(self.config)
        # elif provider_name == "groq":
        #     return GroqLlamaProvider(self.config)
        # elif provider_name == "anthropic":
        #     return AnthropicClaudeProvider(self.config)
        else:
            raise ValueError(f"Unknown extraction provider: {provider_name}")

    async def extract(
        self,
        transcript: str,
        patient: Patient,
        previous_extraction: Optional[ExtractionResult] = None
    ) -> ExtractionResult:
        """
        Extract structured clinical data from transcript

        Args:
            transcript: New transcript text
            patient: Patient information
            previous_extraction: Previous extraction to merge with

        Returns:
            Updated extraction result
        """
        try:
            extraction = await self.provider.extract(
                transcript=transcript,
                patient=patient,
                previous_extraction=previous_extraction
            )
            return extraction
        except Exception as e:
            self.logger.error(f"Extraction failed: {e}")
            raise
```

#### 5. Session Manager (services/session_manager.py)

```python
from typing import Dict
import uuid
from src.models.patient import Patient
from src.models.consultation import ConsultationSession

class SessionManager:
    """
    Manages consultation sessions

    Responsibilities:
    - Create new sessions
    - Retrieve active sessions
    - End sessions and cleanup

    Note: For MVP, sessions are stored in memory (lost on restart)
    """

    def __init__(self):
        self.active_sessions: Dict[str, ConsultationSession] = {}

    def create_session(self, patient: Patient) -> ConsultationSession:
        """Create new consultation session"""
        session_id = str(uuid.uuid4())
        session = ConsultationSession(
            session_id=session_id,
            patient=patient
        )
        self.active_sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> ConsultationSession:
        """Get active session by ID"""
        return self.active_sessions.get(session_id)

    def end_session(self, session_id: str):
        """End session and remove from memory"""
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]
```

### API Error Handling

```python
# Centralized error handling

class TranscriptionError(Exception):
    """Raised when transcription fails"""
    pass

class ExtractionError(Exception):
    """Raised when extraction fails"""
    pass

class SessionError(Exception):
    """Raised when session management fails"""
    pass

# In WebSocket handler
try:
    transcript = await self.transcription_service.transcribe(audio)
except TranscriptionError as e:
    await websocket.send_json({
        "type": "error",
        "error_code": "TRANSCRIPTION_FAILED",
        "message": str(e),
        "recoverable": True  # Frontend can retry
    })
```

### Logging Strategy

```python
# logging_config.py
import logging

def setup_logging():
    """Configure logging for the application"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),  # Console
            logging.FileHandler('logs/drTranscribe.log')  # File
        ]
    )

# Key log points:
# - Session start/end
# - Audio chunk received
# - Transcription completed
# - Extraction completed
# - Errors and exceptions
```

---

## Audio Processing Pipeline

### Overview

The audio processing pipeline handles real-time transcription and extraction with 5-8 second latency. Audio is captured in 5-second chunks, processed independently, and results are merged incrementally.

### Pipeline Stages

```
┌────────────────────────────────────────────────────────────────┐
│  Stage 1: Audio Capture (Frontend - Browser)                  │
│  - MediaRecorder API captures from microphone                 │
│  - Buffer size: 5 seconds (timeslice = 5000ms)                │
│  - Format: WebM audio (Opus codec)                            │
│  - Output: Blob of audio data every 5 seconds                 │
└────────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────────┐
│  Stage 2: Encoding (Frontend)                                 │
│  - Convert Blob to Base64 string                              │
│  - Attach metadata (chunk_number, timestamp)                  │
│  - Create JSON message                                        │
└────────────────────────────────────────────────────────────────┘
                         │
                         ▼ WebSocket.send()
┌────────────────────────────────────────────────────────────────┐
│  Stage 3: Decoding (Backend)                                  │
│  - Receive JSON message via WebSocket                         │
│  - Parse JSON                                                 │
│  - Decode Base64 → raw audio bytes                            │
└────────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────────┐
│  Stage 4: Transcription (Backend)                             │
│  - Send audio bytes to TranscriptionService                   │
│  - TranscriptionService routes to provider (OpenAI Whisper)   │
│  - OpenAI Whisper API call: POST /v1/audio/transcriptions     │
│  - Receive transcript text                                    │
│  - Latency: ~1-2 seconds                                      │
└────────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────────┐
│  Stage 5: Extraction (Backend)                                │
│  - Send transcript to ExtractionService                       │
│  - Build prompt with:                                         │
│    • Patient context (name, age, gender)                      │
│    • Previous extraction (for merging)                        │
│    • New transcript chunk                                     │
│  - ExtractionService routes to provider (OpenAI GPT-4)        │
│  - OpenAI GPT-4 API call: POST /v1/chat/completions           │
│  - Receive structured extraction (JSON)                       │
│  - Latency: ~2-4 seconds                                      │
└────────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────────┐
│  Stage 6: Merging (Backend)                                   │
│  - Merge new extraction with session state                    │
│  - Strategy: Append new information, don't replace            │
│  - Update session.extraction                                  │
└────────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────────┐
│  Stage 7: Response (Backend → Frontend)                       │
│  - Create extraction_update message                           │
│  - Send via WebSocket                                         │
│  - Latency: negligible (<10ms)                                │
└────────────────────────────────────────────────────────────────┘
                         │
                         ▼ WebSocket.onmessage()
┌────────────────────────────────────────────────────────────────┐
│  Stage 8: UI Update (Frontend)                                │
│  - Parse extraction_update message                            │
│  - Update DOM elements for each section                       │
│  - Display updated content to user                            │
└────────────────────────────────────────────────────────────────┘

Total Latency: 5-8 seconds (5s buffer + 1-2s transcription + 2-4s extraction)
```

### Audio Format Handling

**Supported Formats:**
- WebM (Opus codec) - Default for Chrome/Firefox MediaRecorder
- MP3 - Fallback for Safari
- WAV - Uncompressed (larger file size)

**Format Conversion (if needed):**
```python
from pydub import AudioSegment
import io

def convert_audio_for_whisper(audio_bytes: bytes, source_format: str = "webm") -> bytes:
    """
    Convert audio to format acceptable by OpenAI Whisper
    Whisper accepts: mp3, mp4, mpeg, mpga, m4a, wav, webm
    """
    audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format=source_format)

    # Export as MP3 (widely supported)
    output = io.BytesIO()
    audio.export(output, format="mp3")
    return output.getvalue()
```

### Incremental Extraction Strategy

```python
# Example: Merging new extraction with existing data

def merge_extraction(
    existing: ExtractionResult,
    new: ExtractionResult
) -> ExtractionResult:
    """
    Merge new extraction with existing session data

    Strategy:
    - Append new information (don't replace)
    - Preserve existing data
    - Handle conflicts (latest wins)
    """
    merged = ExtractionResult(
        chief_complaint=append_text(existing.chief_complaint, new.chief_complaint),
        diagnosis=append_text(existing.diagnosis, new.diagnosis),
        medicine=append_text(existing.medicine, new.medicine),
        advice=append_text(existing.advice, new.advice),
        next_steps=append_text(existing.next_steps, new.next_steps)
    )
    return merged

def append_text(existing: str, new: str) -> str:
    """Append new text to existing, avoiding duplicates"""
    if not new or new.strip() == "":
        return existing
    if not existing or existing.strip() == "":
        return new

    # Simple deduplication: if new is substring of existing, skip
    if new in existing:
        return existing

    # Append with newline separator
    return f"{existing}\n{new}" if existing else new
```

### Error Recovery

```
Error Scenario: OpenAI API timeout during transcription

1. TranscriptionService catches exception
2. Log error with chunk number
3. Retry with exponential backoff (max 3 attempts)
4. If all retries fail:
   - Send error message to frontend
   - Frontend displays error notification
   - Frontend continues buffering next chunk
   - Session continues (skip failed chunk)

Error Scenario: WebSocket connection drops

1. Frontend detects WebSocket close event
2. Attempt to reconnect (max 3 attempts)
3. If reconnection succeeds:
   - Resume session with same session_id
   - Backend restores session state
4. If reconnection fails:
   - Display error to user
   - Stop recording
   - Data is lost (no persistence in MVP)
```

---

## Transcription Service

### Provider Abstraction

**Design Pattern:** Strategy Pattern with Abstract Base Class

```python
# src/providers/base.py
from abc import ABC, abstractmethod

class TranscriptionProvider(ABC):
    """Abstract base class for transcription providers"""

    @abstractmethod
    async def transcribe(self, audio_bytes: bytes) -> str:
        """
        Transcribe audio to text

        Args:
            audio_bytes: Raw audio data

        Returns:
            Transcribed text

        Raises:
            TranscriptionError: If transcription fails
        """
        pass

    @abstractmethod
    def get_supported_formats(self) -> list[str]:
        """Return list of supported audio formats"""
        pass
```

### OpenAI Whisper Implementation

```python
# src/providers/transcription/openai_whisper.py
import openai
import io
from src.providers.base import TranscriptionProvider
from src.config.settings import Config

class OpenAIWhisperProvider(TranscriptionProvider):
    """
    OpenAI Whisper API implementation

    API Documentation: https://platform.openai.com/docs/api-reference/audio
    """

    def __init__(self, config: Config):
        self.config = config
        self.api_key = config.openai.api_key
        self.model = config.transcription.model  # "whisper-1"

        # Initialize OpenAI client
        openai.api_key = self.api_key

    async def transcribe(self, audio_bytes: bytes) -> str:
        """
        Transcribe audio using OpenAI Whisper API

        API Call:
        POST https://api.openai.com/v1/audio/transcriptions
        Content-Type: multipart/form-data

        Request:
        - file: audio file (mp3, mp4, mpeg, mpga, m4a, wav, webm)
        - model: "whisper-1"
        - language: optional (auto-detect if omitted)
        - response_format: "json" | "text" | "srt" | "verbose_json" | "vtt"

        Response (JSON):
        {
          "text": "Transcribed text here"
        }
        """
        try:
            # Create file-like object from bytes
            audio_file = io.BytesIO(audio_bytes)
            audio_file.name = "audio.webm"  # Required for API

            # Call OpenAI Whisper API
            response = await openai.Audio.atranscribe(
                model=self.model,
                file=audio_file,
                response_format="json"
            )

            transcript = response["text"]
            return transcript

        except openai.error.APIError as e:
            raise TranscriptionError(f"OpenAI API error: {e}")
        except openai.error.Timeout as e:
            raise TranscriptionError(f"OpenAI API timeout: {e}")
        except Exception as e:
            raise TranscriptionError(f"Transcription failed: {e}")

    def get_supported_formats(self) -> list[str]:
        """OpenAI Whisper supports multiple formats"""
        return ["mp3", "mp4", "mpeg", "mpga", "m4a", "wav", "webm"]
```

### Future Providers (Placeholder)

```python
# src/providers/transcription/groq_whisper.py (NOT IMPLEMENTED IN MVP)
class GroqWhisperProvider(TranscriptionProvider):
    """Groq Whisper implementation (faster, cheaper than OpenAI)"""

    async def transcribe(self, audio_bytes: bytes) -> str:
        # POST https://api.groq.com/openai/v1/audio/transcriptions
        pass

# src/providers/transcription/deepgram.py (NOT IMPLEMENTED IN MVP)
class DeepgramProvider(TranscriptionProvider):
    """Deepgram Nova-2 implementation (streaming-optimized)"""

    async def transcribe(self, audio_bytes: bytes) -> str:
        # POST https://api.deepgram.com/v1/listen
        pass
```

### Cost Estimation

**OpenAI Whisper Pricing:**
- $0.006 per minute of audio
- Average consultation: 10 minutes = $0.06
- 1000 consultations/month = $60/month

**Groq Whisper Pricing (Future):**
- $0.00002 per second = $0.0012 per minute
- Average consultation: 10 minutes = $0.012
- 1000 consultations/month = $12/month (5x cheaper than OpenAI)

---

## Structured Extraction Service

### Provider Abstraction

```python
# src/providers/base.py
from abc import ABC, abstractmethod
from typing import Optional
from src.models.patient import Patient
from src.models.extraction import ExtractionResult

class ExtractionProvider(ABC):
    """Abstract base class for extraction providers"""

    @abstractmethod
    async def extract(
        self,
        transcript: str,
        patient: Patient,
        previous_extraction: Optional[ExtractionResult] = None
    ) -> ExtractionResult:
        """
        Extract structured clinical data from transcript

        Args:
            transcript: New transcript text
            patient: Patient information
            previous_extraction: Previous extraction to merge with

        Returns:
            ExtractionResult with 5 sections

        Raises:
            ExtractionError: If extraction fails
        """
        pass
```

### OpenAI GPT-4 Implementation

```python
# src/providers/extraction/openai_gpt.py
import openai
import json
from typing import Optional
from src.providers.base import ExtractionProvider
from src.models.patient import Patient
from src.models.extraction import ExtractionResult
from src.config.settings import Config

class OpenAIGPTProvider(ExtractionProvider):
    """
    OpenAI GPT-4 implementation for structured extraction

    API Documentation: https://platform.openai.com/docs/api-reference/chat
    """

    def __init__(self, config: Config):
        self.config = config
        self.api_key = config.openai.api_key
        self.model = config.extraction.model  # "gpt-4" or "gpt-4-turbo"
        self.temperature = config.extraction.temperature  # 0.3 for consistency

        openai.api_key = self.api_key

    async def extract(
        self,
        transcript: str,
        patient: Patient,
        previous_extraction: Optional[ExtractionResult] = None
    ) -> ExtractionResult:
        """
        Extract structured data using GPT-4

        API Call:
        POST https://api.openai.com/v1/chat/completions

        Request:
        {
          "model": "gpt-4",
          "messages": [
            {"role": "system", "content": "...extraction instructions..."},
            {"role": "user", "content": "...transcript..."}
          ],
          "temperature": 0.3,
          "response_format": {"type": "json_object"}
        }

        Response:
        {
          "choices": [{
            "message": {
              "content": "{\"chief_complaint\": \"...\", \"diagnosis\": \"...\"}"
            }
          }]
        }
        """
        try:
            # Build prompt
            system_prompt = self._build_system_prompt()
            user_prompt = self._build_user_prompt(transcript, patient, previous_extraction)

            # Call OpenAI GPT-4
            response = await openai.ChatCompletion.acreate(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=self.temperature,
                response_format={"type": "json_object"}  # Force JSON output
            )

            # Parse JSON response
            content = response.choices[0].message.content
            data = json.loads(content)

            # Create ExtractionResult
            extraction = ExtractionResult(
                chief_complaint=data.get("chief_complaint", ""),
                diagnosis=data.get("diagnosis", ""),
                medicine=data.get("medicine", ""),
                advice=data.get("advice", ""),
                next_steps=data.get("next_steps", "")
            )

            return extraction

        except openai.error.APIError as e:
            raise ExtractionError(f"OpenAI API error: {e}")
        except json.JSONDecodeError as e:
            raise ExtractionError(f"Failed to parse GPT-4 response: {e}")
        except Exception as e:
            raise ExtractionError(f"Extraction failed: {e}")

    def _build_system_prompt(self) -> str:
        """
        Build system prompt with extraction instructions

        Critical: Clear instructions for 5-section extraction
        """
        return """You are a medical transcription assistant. Your task is to extract structured clinical information from doctor-patient conversation transcripts.

Extract information into these 5 sections:

1. **Chief Complaint**: Patient's primary reason for visit. What brought them to the doctor?
   Example: "Headache for 3 days", "Fever and cough"

2. **Diagnosis**: Doctor's assessment or diagnosis of the patient's condition.
   Example: "Viral fever", "Migraine", "Upper respiratory infection"

3. **Medicine**: Medications prescribed by the doctor, including dosage and frequency.
   Example: "Paracetamol 500mg twice daily for 3 days"

4. **Advice**: General advice given by the doctor (lifestyle, diet, rest, etc.)
   Example: "Drink plenty of fluids", "Rest for 3 days", "Avoid cold drinks"

5. **Next Steps**: Follow-up actions required.
   Sub-categories:
   - Lab Tests: Any tests ordered (blood test, X-ray, etc.)
   - Follow-up: When to come back for next visit
   - Cross-consultation: Referral to another doctor/specialist

**Important Instructions:**
- Extract ONLY information explicitly mentioned in the transcript
- If a section has no information, return empty string ""
- Be concise and medically accurate
- Merge with previous extraction if provided (append new information)
- Return response as JSON with these exact keys:
  {
    "chief_complaint": "...",
    "diagnosis": "...",
    "medicine": "...",
    "advice": "...",
    "next_steps": "..."
  }
"""

    def _build_user_prompt(
        self,
        transcript: str,
        patient: Patient,
        previous_extraction: Optional[ExtractionResult]
    ) -> str:
        """Build user prompt with transcript and context"""

        prompt = f"""**Patient Information:**
- Name: {patient.name}
- Age: {patient.age}
- Gender: {patient.gender}

**New Transcript:**
{transcript}
"""

        if previous_extraction:
            prompt += f"""

**Previous Extraction (to merge with):**
- Chief Complaint: {previous_extraction.chief_complaint}
- Diagnosis: {previous_extraction.diagnosis}
- Medicine: {previous_extraction.medicine}
- Advice: {previous_extraction.advice}
- Next Steps: {previous_extraction.next_steps}

**Instructions:** Merge the new transcript information with the previous extraction. Append new information, don't replace existing data.
"""

        prompt += "\n\n**Extract the clinical information into JSON format:**"
        return prompt
```

### Extraction Prompt Engineering Tips

```
Key Principles:
1. Clear Section Definitions: Define each section with examples
2. Merge Strategy: Explicitly instruct to append, not replace
3. JSON Format: Force JSON output for reliable parsing
4. Temperature: Use low temperature (0.3) for consistency
5. Examples: Provide few-shot examples in system prompt

Common Issues:
- Hallucination: Model invents information not in transcript
  → Solution: Emphasize "ONLY information explicitly mentioned"

- Overwriting: Model replaces previous data instead of merging
  → Solution: Pass previous extraction, instruct to "append"

- Inconsistent Format: Model doesn't follow JSON structure
  → Solution: Use response_format={"type": "json_object"}

- Poor Section Assignment: Model puts info in wrong section
  → Solution: Provide clear examples for each section
```

### Future Providers (Placeholder)

```python
# src/providers/extraction/groq_llama.py (NOT IMPLEMENTED IN MVP)
class GroqLlamaProvider(ExtractionProvider):
    """
    Groq Llama-3.1 implementation (faster, cheaper than GPT-4)

    Groq provides ~10x faster inference than OpenAI
    Cost: ~$0.10 per 1M tokens (10x cheaper than GPT-4)
    """
    async def extract(...) -> ExtractionResult:
        # POST https://api.groq.com/openai/v1/chat/completions
        pass
```

### Cost Estimation

**OpenAI GPT-4 Pricing:**
- Input: $10 per 1M tokens
- Output: $30 per 1M tokens
- Average extraction: ~500 input tokens, ~200 output tokens
- Cost per extraction: ~$0.011
- 1000 consultations (avg 5 chunks each): ~$55/month

**Groq Llama-3.1 Pricing (Future):**
- $0.10 per 1M tokens (both input and output)
- Average extraction: ~700 total tokens
- Cost per extraction: ~$0.00007
- 1000 consultations (5 chunks each): ~$0.35/month (150x cheaper!)

---

## Data Models

All data models use **Pydantic** for validation and serialization.

### Patient Model

```python
# src/models/patient.py
from pydantic import BaseModel, Field

class Patient(BaseModel):
    """Patient information collected at session start"""

    name: str = Field(..., min_length=1, max_length=100, description="Patient full name")
    age: int = Field(..., ge=0, le=150, description="Patient age in years")
    gender: str = Field(..., pattern="^(Male|Female|Other)$", description="Patient gender")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "John Doe",
                "age": 45,
                "gender": "Male"
            }
        }
```

### Extraction Result Model

```python
# src/models/extraction.py
from pydantic import BaseModel, Field

class ExtractionResult(BaseModel):
    """Structured clinical data extraction"""

    chief_complaint: str = Field(default="", description="Patient's primary reason for visit")
    diagnosis: str = Field(default="", description="Doctor's assessment/diagnosis")
    medicine: str = Field(default="", description="Medications prescribed with dosage")
    advice: str = Field(default="", description="General advice (lifestyle, diet, rest)")
    next_steps: str = Field(default="", description="Follow-up actions (lab tests, follow-up, referrals)")

    class Config:
        json_schema_extra = {
            "example": {
                "chief_complaint": "Headache for 3 days, worsening in the morning",
                "diagnosis": "Migraine (tentative)",
                "medicine": "Ibuprofen 400mg twice daily after meals for 5 days",
                "advice": "Rest in dark room, avoid bright screens, stay hydrated",
                "next_steps": "Lab Tests: None\nFollow-up: If no improvement in 48 hours\nCross-consultation: Neurologist if headache persists beyond 1 week"
            }
        }
```

### Consultation Session Model

```python
# src/models/consultation.py
from pydantic import BaseModel, Field
from typing import List
from datetime import datetime
from src.models.patient import Patient
from src.models.extraction import ExtractionResult

class ConsultationSession(BaseModel):
    """Consultation session state (in-memory for MVP)"""

    session_id: str = Field(..., description="Unique session identifier (UUID)")
    patient: Patient = Field(..., description="Patient information")
    started_at: datetime = Field(default_factory=datetime.utcnow, description="Session start time")
    transcript_chunks: List[str] = Field(default_factory=list, description="All transcript chunks")
    extraction: ExtractionResult = Field(default_factory=ExtractionResult, description="Current extraction state")

    def add_transcript_chunk(self, chunk: str):
        """Append new transcript chunk"""
        self.transcript_chunks.append(chunk)

    def update_extraction(self, new_extraction: ExtractionResult):
        """Update extraction with merging logic"""
        self.extraction = self._merge_extractions(self.extraction, new_extraction)

    def _merge_extractions(
        self,
        existing: ExtractionResult,
        new: ExtractionResult
    ) -> ExtractionResult:
        """Merge new extraction with existing (append strategy)"""
        return ExtractionResult(
            chief_complaint=self._append_text(existing.chief_complaint, new.chief_complaint),
            diagnosis=self._append_text(existing.diagnosis, new.diagnosis),
            medicine=self._append_text(existing.medicine, new.medicine),
            advice=self._append_text(existing.advice, new.advice),
            next_steps=self._append_text(existing.next_steps, new.next_steps)
        )

    @staticmethod
    def _append_text(existing: str, new: str) -> str:
        """Append new text to existing, avoiding duplicates"""
        if not new or new.strip() == "":
            return existing
        if not existing or existing.strip() == "":
            return new
        if new in existing:
            return existing
        return f"{existing}\n{new}"

    def get_full_transcript(self) -> str:
        """Get complete transcript from all chunks"""
        return "\n".join(self.transcript_chunks)

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "550e8400-e29b-41d4-a716-446655440000",
                "patient": {
                    "name": "John Doe",
                    "age": 45,
                    "gender": "Male"
                },
                "started_at": "2026-02-05T10:30:00Z",
                "transcript_chunks": [
                    "Doctor: Hello, what brings you in today?",
                    "Patient: I've had a headache for the past 3 days..."
                ],
                "extraction": {
                    "chief_complaint": "Headache for 3 days",
                    "diagnosis": "",
                    "medicine": "",
                    "advice": "",
                    "next_steps": ""
                }
            }
        }
```

### WebSocket Message Models

```python
# src/models/websocket_messages.py
from pydantic import BaseModel
from typing import Literal
from datetime import datetime
from src.models.patient import Patient
from src.models.extraction import ExtractionResult

class StartSessionMessage(BaseModel):
    """Message to start new consultation session"""
    type: Literal["start_session"] = "start_session"
    patient: Patient

class AudioChunkMessage(BaseModel):
    """Message containing audio chunk"""
    type: Literal["audio_chunk"] = "audio_chunk"
    audio: str  # Base64-encoded audio
    chunk_number: int
    timestamp: datetime

class StopSessionMessage(BaseModel):
    """Message to end consultation session"""
    type: Literal["stop_session"] = "stop_session"

class ExtractionUpdateMessage(BaseModel):
    """Message with extraction update from backend"""
    type: Literal["extraction_update"] = "extraction_update"
    data: ExtractionResult
    chunk_number: int
    timestamp: datetime

class ErrorMessage(BaseModel):
    """Error message from backend"""
    type: Literal["error"] = "error"
    message: str
    error_code: str = ""
    recoverable: bool = False
```

---

## Configuration Management

### Configuration File Structure

```yaml
# config/settings.yaml

# Transcription configuration
transcription:
  provider: "openai"  # Options: "openai", "groq", "deepgram"
  model: "whisper-1"

# Extraction configuration
extraction:
  provider: "openai"  # Options: "openai", "groq", "anthropic"
  model: "gpt-4"
  temperature: 0.3    # Low temperature for consistency

# OpenAI API credentials
openai:
  api_key: "${OPENAI_API_KEY}"  # Load from environment variable

# Groq API credentials (future)
groq:
  api_key: "${GROQ_API_KEY}"

# Deepgram API credentials (future)
deepgram:
  api_key: "${DEEPGRAM_API_KEY}"

# Server configuration
server:
  host: "0.0.0.0"
  port: 8000
  debug: false

# Logging configuration
logging:
  level: "INFO"
  file: "logs/drTranscribe.log"
```

### Configuration Loading

```python
# src/config/settings.py
import yaml
import os
from pydantic import BaseModel
from typing import Optional

class TranscriptionConfig(BaseModel):
    provider: str
    model: str

class ExtractionConfig(BaseModel):
    provider: str
    model: str
    temperature: float

class OpenAIConfig(BaseModel):
    api_key: str

class GroqConfig(BaseModel):
    api_key: Optional[str] = None

class DeepgramConfig(BaseModel):
    api_key: Optional[str] = None

class ServerConfig(BaseModel):
    host: str
    port: int
    debug: bool

class LoggingConfig(BaseModel):
    level: str
    file: str

class Config(BaseModel):
    """Complete application configuration"""
    transcription: TranscriptionConfig
    extraction: ExtractionConfig
    openai: OpenAIConfig
    groq: Optional[GroqConfig] = None
    deepgram: Optional[DeepgramConfig] = None
    server: ServerConfig
    logging: LoggingConfig

def load_config(config_path: str = "config/settings.yaml") -> Config:
    """
    Load configuration from YAML file with environment variable substitution

    Environment variables are substituted for ${VAR_NAME} placeholders
    Example: api_key: "${OPENAI_API_KEY}" → api_key: "sk-..."
    """
    with open(config_path, "r") as f:
        config_dict = yaml.safe_load(f)

    # Substitute environment variables
    config_dict = substitute_env_vars(config_dict)

    # Validate and load into Pydantic model
    config = Config(**config_dict)
    return config

def substitute_env_vars(data):
    """Recursively substitute ${VAR_NAME} with environment variables"""
    if isinstance(data, dict):
        return {k: substitute_env_vars(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [substitute_env_vars(item) for item in data]
    elif isinstance(data, str) and data.startswith("${") and data.endswith("}"):
        var_name = data[2:-1]
        return os.getenv(var_name, data)
    else:
        return data
```

### Environment Variables

```bash
# .env (NOT COMMITTED TO GIT)
OPENAI_API_KEY=sk-...your_openai_key...
GROQ_API_KEY=gsk_...your_groq_key...
DEEPGRAM_API_KEY=...your_deepgram_key...
```

### Configuration Usage

```python
# In services
from src.config.settings import load_config

config = load_config()

# Access configuration
transcription_provider = config.transcription.provider
openai_key = config.openai.api_key
temperature = config.extraction.temperature
```

### Switching Providers

To switch from OpenAI to Groq (future):

```yaml
# config/settings.yaml
transcription:
  provider: "groq"  # Change from "openai" to "groq"
  model: "whisper-large-v3"

extraction:
  provider: "groq"  # Change from "openai" to "groq"
  model: "llama-3.1-70b-versatile"
  temperature: 0.3

groq:
  api_key: "${GROQ_API_KEY}"
```

**No code changes required!** The factory pattern loads the correct provider based on configuration.

---

## Deployment Guide

### Prerequisites

- Python 3.11+
- Docker and Docker Compose (optional, for containerized deployment)
- OpenAI API key

### Local Development Setup

```bash
# 1. Clone repository
cd drTranscribe

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create configuration
cp config/settings.example.yaml config/settings.yaml

# 5. Set environment variables
export OPENAI_API_KEY=sk-...your_key...

# 6. Run application
python src/main.py

# 7. Open browser
# Navigate to: http://localhost:8000
```

### Requirements File

```txt
# requirements.txt
fastapi==0.115.6
uvicorn[standard]==0.34.0
pydantic==2.10.5
pydantic-settings==2.7.0
openai==1.58.1
pyyaml==6.0.2
python-multipart==0.0.18
websockets==14.1
```

### Docker Deployment

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY frontend/ ./frontend/
COPY config/ ./config/

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```yaml
# docker-compose.yml
version: '3.8'

services:
  drtranscribe:
    build: .
    ports:
      - "8000:8000"
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    volumes:
      - ./logs:/app/logs
    restart: unless-stopped

volumes:
  logs:
```

```bash
# Run with Docker Compose
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

### Environment Variables

Create `.env` file (NOT committed to git):

```bash
# .env
OPENAI_API_KEY=sk-proj-...your_openai_key...

# Future providers (when implemented)
GROQ_API_KEY=gsk_...your_groq_key...
DEEPGRAM_API_KEY=...your_deepgram_key...
```

### Health Check

```bash
# Check if service is running
curl http://localhost:8000/health

# Expected response:
# {"status":"healthy","service":"drTranscribe MVP"}
```

### Testing

```bash
# Run unit tests (when implemented)
pytest tests/

# Test WebSocket endpoint
wscat -c ws://localhost:8000/ws
```

### Monitoring

```bash
# View logs
tail -f logs/drTranscribe.log

# Monitor system resources
docker stats  # If using Docker
```

### Troubleshooting

**Issue: WebSocket connection fails**
```
Solution: Ensure backend is running on http://localhost:8000
Check CORS settings in FastAPI if frontend is on different domain
```

**Issue: Microphone permission denied**
```
Solution: Browser requires HTTPS for microphone access (except localhost)
For local dev, use localhost (not 127.0.0.1 or IP address)
```

**Issue: OpenAI API timeout**
```
Solution: Check API key is valid
Check internet connection
Increase timeout in OpenAI client configuration
```

**Issue: Poor transcription quality**
```
Solution: Ensure good audio quality (reduce background noise)
Use better microphone if possible
Adjust chunk size (try 10 seconds instead of 5)
```

---

## Design Patterns & Principles

### Design Patterns Applied

#### 1. Strategy Pattern
**Used in:** Transcription and Extraction services

**Purpose:** Allow runtime selection of algorithms (providers) based on configuration

**Implementation:**
```python
# Abstract interface
class TranscriptionProvider(ABC):
    @abstractmethod
    async def transcribe(self, audio_bytes: bytes) -> str:
        pass

# Concrete implementations
class OpenAIWhisperProvider(TranscriptionProvider):
    async def transcribe(self, audio_bytes: bytes) -> str:
        # OpenAI-specific implementation
        pass

class GroqWhisperProvider(TranscriptionProvider):
    async def transcribe(self, audio_bytes: bytes) -> str:
        # Groq-specific implementation
        pass

# Context uses strategy
class TranscriptionService:
    def __init__(self, config):
        self.provider = self._load_provider(config)  # Strategy selection

    async def transcribe(self, audio):
        return await self.provider.transcribe(audio)  # Delegate to strategy
```

**Benefits:**
- ✅ Easy to add new providers (Groq, Deepgram) without changing existing code
- ✅ Switch providers via configuration (no code changes)
- ✅ Testable (mock providers in tests)

#### 2. Factory Pattern
**Used in:** Provider instantiation

**Purpose:** Create provider instances based on configuration

**Implementation:**
```python
class TranscriptionProviderFactory:
    @staticmethod
    def create(provider_name: str, config: Config) -> TranscriptionProvider:
        if provider_name == "openai":
            return OpenAIWhisperProvider(config)
        elif provider_name == "groq":
            return GroqWhisperProvider(config)
        elif provider_name == "deepgram":
            return DeepgramProvider(config)
        else:
            raise ValueError(f"Unknown provider: {provider_name}")
```

**Benefits:**
- ✅ Centralized object creation
- ✅ Easy to add new providers
- ✅ Configuration-driven instantiation

#### 3. Singleton Pattern (Implicit)
**Used in:** Session Manager, Configuration

**Purpose:** Ensure single instance of certain components

**Implementation:**
```python
# In FastAPI, services are created once at startup
config = load_config()  # Load once
ws_handler = WebSocketHandler(config)  # Single instance

# All WebSocket connections use same handler instance
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_handler.handle_connection(websocket)
```

**Benefits:**
- ✅ Shared state (session manager tracks all sessions)
- ✅ Resource efficiency (one OpenAI client, not per request)

#### 4. Dependency Injection
**Used in:** Service dependencies

**Purpose:** Loose coupling between components

**Implementation:**
```python
class WebSocketHandler:
    def __init__(self, config: Config):
        # Dependencies injected via constructor
        self.transcription_service = TranscriptionService(config)
        self.extraction_service = ExtractionService(config)
        self.session_manager = SessionManager()

# Easy to test with mocks
class TestWebSocketHandler:
    def test_handle_audio(self):
        mock_transcription = MockTranscriptionService()
        mock_extraction = MockExtractionService()
        handler = WebSocketHandler(mock_transcription, mock_extraction)
        # ... test with mocks
```

**Benefits:**
- ✅ Testable (inject mocks)
- ✅ Flexible (swap implementations)
- ✅ Explicit dependencies (clear in constructor)

### SOLID Principles

#### S - Single Responsibility Principle
**Each class has one reason to change**

Examples:
- `TranscriptionService`: Only handles transcription (not extraction)
- `ExtractionService`: Only handles extraction (not transcription)
- `SessionManager`: Only manages session lifecycle (not audio processing)
- `WebSocketHandler`: Only handles WebSocket protocol (delegates to services)

#### O - Open/Closed Principle
**Open for extension, closed for modification**

Example: Adding new provider
```python
# To add Groq provider, NO changes to existing code:
# 1. Create new class (extension)
class GroqWhisperProvider(TranscriptionProvider):
    async def transcribe(self, audio_bytes: bytes) -> str:
        pass

# 2. Update factory (one line added)
# 3. Update config (change provider name)
# 4. DONE - no changes to TranscriptionService, WebSocketHandler, etc.
```

#### L - Liskov Substitution Principle
**Subclasses must be substitutable for base class**

Example:
```python
# Any TranscriptionProvider can be used interchangeably
provider: TranscriptionProvider = OpenAIWhisperProvider(config)
# OR
provider: TranscriptionProvider = GroqWhisperProvider(config)

# Both work the same way
transcript = await provider.transcribe(audio)
```

#### I - Interface Segregation Principle
**Clients shouldn't depend on unused interfaces**

Example:
- `TranscriptionProvider` has only `transcribe()` (not extraction methods)
- `ExtractionProvider` has only `extract()` (not transcription methods)
- Each interface is minimal and focused

#### D - Dependency Inversion Principle
**Depend on abstractions, not concretions**

Example:
```python
# WebSocketHandler depends on ABSTRACT TranscriptionService
# NOT on concrete OpenAIWhisperProvider
class WebSocketHandler:
    def __init__(self, config: Config):
        # Depends on abstraction (TranscriptionService)
        self.transcription_service = TranscriptionService(config)
        # TranscriptionService internally uses concrete provider
        # But WebSocketHandler doesn't know or care which one
```

### Other Principles

#### KISS (Keep It Simple, Stupid)
**MVP keeps it simple:**
- No database (in-memory sessions)
- No authentication (single-user)
- No advanced audio processing (raw chunks)
- Simple HTML/CSS/JS (no framework)

#### DRY (Don't Repeat Yourself)
**Code reuse examples:**
- Provider abstraction used for both transcription AND extraction
- Merge logic centralized in `ConsultationSession._merge_extractions()`
- Configuration loading reused across all services

#### YAGNI (You Aren't Gonna Need It)
**Not implemented in MVP:**
- Multi-user support (YAGNI - add when needed)
- Database persistence (YAGNI - MVP discards data)
- Real-time transcript display (YAGNI - focus on extraction)
- Advanced audio processing (YAGNI - Whisper handles it)

### Code Organization Principles

```
✅ DO:
- Keep related code together (providers/transcription/, providers/extraction/)
- Use clear, descriptive names (TranscriptionService, not TS)
- Document complex logic (prompt engineering, merging)
- Use type hints everywhere (audio_bytes: bytes)
- Handle errors explicitly (try/except with specific exceptions)

❌ DON'T:
- Mix concerns (don't put extraction logic in WebSocketHandler)
- Use magic numbers (5000ms → const CHUNK_DURATION_MS)
- Swallow exceptions (except: pass)
- Repeat code (extract common logic into methods)
- Over-engineer (keep MVP scope limited)
```

---

## Future Extensibility

### Phase 2: Post-MVP Enhancements

#### 1. Database Persistence
**Goal:** Save consultation data for later review

```python
# Add PostgreSQL/SQLite database
# Store: consultations, patients, transcripts, extractions

# Database schema:
CREATE TABLE patients (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100),
    age INT,
    gender VARCHAR(10),
    created_at TIMESTAMP
);

CREATE TABLE consultations (
    id UUID PRIMARY KEY,
    patient_id INT REFERENCES patients(id),
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    full_transcript TEXT,
    chief_complaint TEXT,
    diagnosis TEXT,
    medicine TEXT,
    advice TEXT,
    next_steps TEXT
);

# Changes required:
# - Add database models (SQLAlchemy/Tortoise ORM)
# - Modify SessionManager to save to database
# - Add API endpoints: GET /consultations, GET /consultations/{id}
```

#### 2. User Authentication
**Goal:** Multi-user support with doctor accounts

```python
# Add JWT authentication
# - Doctor registration/login
# - Session tokens
# - Role-based access control (doctor, admin)

# Changes required:
# - Add User model with password hashing
# - Add authentication middleware
# - Protect WebSocket endpoint (require token)
# - Associate consultations with doctors
```

#### 3. Patient History Integration
**Goal:** Show previous consultations during session

```python
# Vector database for semantic search (Chroma/Pinecone)
# - Store consultation embeddings
# - Search similar cases
# - Retrieve patient history

# Changes required:
# - Add vector database client
# - Generate embeddings from consultations
# - Add API endpoint: GET /patients/{id}/history
# - Display history in frontend during session
```

#### 4. Real-Time Transcript Display
**Goal:** Show live transcript as doctor speaks

```python
# Add transcript display alongside extraction sections
# - Stream transcript text in real-time
# - Highlight medical entities (color-coded)
# - Allow manual editing

# Changes required:
# - Add transcript section to frontend
# - Send transcript text in WebSocket messages
# - Add text highlighting with medical NER
```

#### 5. Advanced Audio Processing
**Goal:** Improve audio quality and reduce noise

```python
# Add audio preprocessing pipeline
# - Noise reduction (noisereduce library)
# - Voice activity detection (webrtcvad)
# - Speaker diarization (distinguish doctor vs patient)

# Changes required:
# - Add audio preprocessing service
# - Process audio before transcription
# - Tag transcript with speaker labels
```

#### 6. Multi-Language Support
**Goal:** Support consultations in multiple languages

```python
# Extend to support Hindi, Tamil, Bengali, etc.
# - Language detection
# - Language-specific prompts
# - Bilingual extraction (Hindi diagnosis → English medical terms)

# Changes required:
# - Add language detection (langdetect)
# - Language-specific extraction prompts
# - UI language selection
```

#### 7. Offline Mode
**Goal:** Work without internet (local models)

```python
# Deploy local Whisper and Llama models
# - faster-whisper (local transcription)
# - Ollama/llama.cpp (local extraction)

# Changes required:
# - Add local model providers
# - Model download and setup scripts
# - Fallback to cloud when local fails
```

#### 8. Mobile App
**Goal:** Native mobile app for iOS/Android

```python
# React Native mobile app
# - Better audio capture (native APIs)
# - Offline support
# - Bluetooth headset integration

# Technology:
# - React Native
# - WebSocket client
# - Native audio modules
```

### Adding New Providers (Example: Groq)

**Step 1: Implement Provider**
```python
# src/providers/transcription/groq_whisper.py
from groq import Groq
from src.providers.base import TranscriptionProvider

class GroqWhisperProvider(TranscriptionProvider):
    def __init__(self, config: Config):
        self.client = Groq(api_key=config.groq.api_key)
        self.model = config.transcription.model

    async def transcribe(self, audio_bytes: bytes) -> str:
        # Groq API is compatible with OpenAI format
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = "audio.webm"

        response = self.client.audio.transcriptions.create(
            model=self.model,  # "whisper-large-v3"
            file=audio_file,
            response_format="json"
        )

        return response.text

    def get_supported_formats(self) -> list[str]:
        return ["mp3", "mp4", "mpeg", "mpga", "m4a", "wav", "webm"]
```

**Step 2: Register in Factory**
```python
# src/services/transcription_service.py
def _load_provider(self) -> TranscriptionProvider:
    provider_name = self.config.transcription.provider

    if provider_name == "openai":
        return OpenAIWhisperProvider(self.config)
    elif provider_name == "groq":
        return GroqWhisperProvider(self.config)  # ← Add this line
    else:
        raise ValueError(f"Unknown provider: {provider_name}")
```

**Step 3: Update Configuration**
```yaml
# config/settings.yaml
transcription:
  provider: "groq"  # ← Change this
  model: "whisper-large-v3"

groq:
  api_key: "${GROQ_API_KEY}"
```

**Step 4: DONE!**
No other code changes needed. The system automatically uses Groq.

### Scalability Considerations

**Current MVP Limitations:**
- Single server instance
- In-memory sessions (lost on restart)
- No load balancing
- No horizontal scaling

**Future Scaling Architecture:**
```
┌─────────────────────────────────────────────────────────┐
│                    Load Balancer                        │
│              (NGINX / Cloud Load Balancer)              │
└─────────────────────────────────────────────────────────┘
         │                │                │
         ▼                ▼                ▼
    ┌─────────┐    ┌─────────┐    ┌─────────┐
    │ Server 1│    │ Server 2│    │ Server 3│
    │ (FastAPI)    │ (FastAPI)    │ (FastAPI)
    └─────────┘    └─────────┘    └─────────┘
         │                │                │
         └────────────────┼────────────────┘
                          ▼
                  ┌───────────────┐
                  │  Redis Cache  │  ← Shared session storage
                  └───────────────┘
                          │
                          ▼
                  ┌───────────────┐
                  │  PostgreSQL   │  ← Persistent storage
                  └───────────────┘
```

**Changes needed for scale:**
1. Replace in-memory sessions with Redis
2. Add PostgreSQL for persistence
3. Add load balancer (NGINX/ALB)
4. Make servers stateless (no local storage)
5. Add API rate limiting
6. Add request queuing for API calls

### Cost Optimization Strategies

**Current MVP Cost (1000 consultations/month, 10 min avg):**
- Transcription (OpenAI Whisper): ~$60/month
- Extraction (OpenAI GPT-4): ~$55/month
- **Total: ~$115/month**

**Optimized Cost (Groq APIs):**
- Transcription (Groq Whisper): ~$12/month (5x cheaper)
- Extraction (Groq Llama-3.1): ~$0.35/month (150x cheaper!)
- **Total: ~$12/month** (10x cheaper overall)

**Hybrid Approach (Best Balance):**
- Primary: Groq (fast & cheap)
- Fallback: OpenAI (when Groq is rate-limited)
- **Cost: $15-30/month with 99.9% uptime**

---

## Appendices

### Appendix A: API Costs (Detailed)

**OpenAI Whisper API Pricing:**
- Model: `whisper-1`
- Cost: $0.006 per minute
- Example:
  - 1 minute audio → $0.006
  - 10 minute consultation → $0.060
  - 100 consultations/day → $6/day → $180/month

**OpenAI GPT-4 API Pricing:**
- Model: `gpt-4-turbo`
- Input: $10 per 1M tokens
- Output: $30 per 1M tokens
- Example extraction:
  - Input: ~500 tokens (transcript + context)
  - Output: ~200 tokens (structured data)
  - Cost per extraction: ~$0.011
  - 10 minute consultation (5 chunks): 5 × $0.011 = $0.055
  - 100 consultations/day: $5.50/day → $165/month

**Total Monthly Cost (OpenAI only):**
- 1000 consultations/month (avg 10 min): ~$115/month
- 5000 consultations/month: ~$575/month
- 10,000 consultations/month: ~$1,150/month

**Groq API Pricing (Future):**
- Whisper Large V3: $0.00002/second = $0.0012/minute
- Llama-3.1-70B: $0.10 per 1M tokens (input + output)
- Total: ~$12/month for 1000 consultations (10x cheaper!)

### Appendix B: Error Handling

**Error Categories:**

1. **Network Errors**
   - WebSocket disconnection
   - API timeout
   - DNS resolution failure
   - **Handling:** Retry with exponential backoff, fallback to alternative provider

2. **API Errors**
   - Invalid API key (401)
   - Rate limit exceeded (429)
   - Server error (500)
   - **Handling:** Log error, notify user, retry if transient

3. **Validation Errors**
   - Invalid patient data
   - Invalid audio format
   - Malformed JSON
   - **Handling:** Return clear error message to frontend, don't retry

4. **Processing Errors**
   - Transcription failed (poor audio quality)
   - Extraction failed (unparseable response)
   - **Handling:** Log error, send error message to frontend, continue with next chunk

**Error Response Format:**
```json
{
  "type": "error",
  "error_code": "TRANSCRIPTION_FAILED",
  "message": "OpenAI Whisper API timeout after 30 seconds",
  "recoverable": true,
  "chunk_number": 3,
  "timestamp": "2026-02-05T10:30:15Z"
}
```

**Retry Strategy:**
```python
# Exponential backoff with jitter
import asyncio
import random

async def retry_with_backoff(func, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise  # Final attempt failed
            wait_time = (2 ** attempt) + random.uniform(0, 1)
            await asyncio.sleep(wait_time)
```

### Appendix C: Testing Strategy

**Unit Tests:**
```python
# tests/test_transcription_service.py
import pytest
from unittest.mock import AsyncMock, patch
from src.services.transcription_service import TranscriptionService

@pytest.mark.asyncio
async def test_transcribe_success():
    # Mock OpenAI API
    with patch('openai.Audio.atranscribe') as mock_transcribe:
        mock_transcribe.return_value = {"text": "Hello doctor"}

        service = TranscriptionService(mock_config)
        result = await service.transcribe(b"audio_data")

        assert result == "Hello doctor"
        mock_transcribe.assert_called_once()

@pytest.mark.asyncio
async def test_transcribe_api_error():
    with patch('openai.Audio.atranscribe') as mock_transcribe:
        mock_transcribe.side_effect = openai.error.APIError("API Error")

        service = TranscriptionService(mock_config)

        with pytest.raises(TranscriptionError):
            await service.transcribe(b"audio_data")
```

**Integration Tests:**
```python
# tests/test_websocket_handler.py
import pytest
from fastapi.testclient import TestClient
from src.main import app

def test_websocket_flow():
    client = TestClient(app)

    with client.websocket_connect("/ws") as websocket:
        # Send start session
        websocket.send_json({
            "type": "start_session",
            "patient": {"name": "John", "age": 45, "gender": "Male"}
        })

        # Receive session started
        response = websocket.receive_json()
        assert response["type"] == "session_started"

        # Send audio chunk
        websocket.send_json({
            "type": "audio_chunk",
            "audio": "base64_audio_data",
            "chunk_number": 1
        })

        # Receive extraction update
        response = websocket.receive_json()
        assert response["type"] == "extraction_update"
        assert "chief_complaint" in response["data"]
```

**End-to-End Tests:**
```python
# tests/test_e2e.py
import pytest
import asyncio
from playwright.async_api import async_playwright

@pytest.mark.asyncio
async def test_full_consultation_flow():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        # Navigate to app
        await page.goto("http://localhost:8000")

        # Fill patient info
        await page.fill("#patientName", "Test Patient")
        await page.fill("#patientAge", "30")
        await page.select_option("#patientGender", "Male")

        # Start recording (requires microphone permissions in test)
        await page.click("#startBtn")

        # Wait for extraction updates
        await page.wait_for_selector("#chiefComplaint:not(:empty)")

        # Stop recording
        await page.click("#stopBtn")

        # Verify extraction sections populated
        chief_complaint = await page.inner_text("#chiefComplaint")
        assert len(chief_complaint) > 0

        await browser.close()
```

**Test Coverage Goals:**
- Unit tests: 80%+ coverage
- Integration tests: Critical paths (WebSocket flow, API calls)
- E2E tests: Main user journey (start → record → extract → stop)

### Appendix D: Security Considerations

**API Key Security:**
- ✅ Store in environment variables (never commit to git)
- ✅ Use `.env` file locally (add to `.gitignore`)
- ✅ Use secret management in production (AWS Secrets Manager, GCP Secret Manager)

**Patient Data Privacy:**
- ⚠️ MVP: No persistence (data lost after session)
- ⚠️ Future: Encrypt data at rest and in transit
- ⚠️ Future: HIPAA compliance (BAA with cloud providers)
- ⚠️ Future: Anonymization for non-clinical use

**WebSocket Security:**
- ⚠️ MVP: No authentication
- ⚠️ Future: JWT tokens for authentication
- ⚠️ Future: WSS (WebSocket Secure) with TLS
- ⚠️ Future: Rate limiting per user

**HTTPS Requirement:**
- ✅ Browser requires HTTPS for microphone access
- ✅ localhost exempt (for development)
- ✅ Production: Use Let's Encrypt or cloud TLS termination

### Appendix E: Performance Benchmarks

**Latency Breakdown (Typical):**
```
Audio buffering:       5000ms  (fixed, user-configured)
WebSocket transfer:      10ms  (negligible)
Transcription (OpenAI):1500ms  (varies by audio quality)
Extraction (GPT-4):    2500ms  (varies by transcript length)
Response transfer:       10ms  (negligible)
─────────────────────────────
Total:                ~9000ms  (9 seconds)
```

**Optimization Opportunities:**
- Use Groq Whisper: 500ms transcription (3x faster)
- Use Groq Llama: 800ms extraction (3x faster)
- **Optimized total: ~6300ms (6.3 seconds)**

**Concurrent Sessions:**
- MVP: 1 session at a time (single-user)
- Future: 100+ concurrent sessions (with proper infrastructure)

**Memory Usage:**
- Per session: ~50MB (audio buffers + session state)
- 10 concurrent sessions: ~500MB
- 100 concurrent sessions: ~5GB (add Redis for session storage)

### Appendix F: Development Roadmap

**Week 1-2: MVP Foundation**
- ✅ Basic FastAPI backend
- ✅ WebSocket handler
- ✅ OpenAI Whisper integration
- ✅ OpenAI GPT-4 extraction
- ✅ Simple HTML/CSS frontend
- ✅ 5-second audio chunking

**Week 3-4: Refinement**
- Error handling improvements
- Retry logic with exponential backoff
- Better UI feedback (loading states)
- Logging and debugging

**Month 2: Provider Flexibility**
- Add Groq Whisper provider
- Add Groq Llama extraction
- Multi-provider fallback
- Cost comparison dashboard

**Month 3: Data Persistence**
- PostgreSQL integration
- Consultation history
- Patient records
- Search and filtering

**Month 4: Advanced Features**
- User authentication (JWT)
- Multi-user support
- Real-time transcript display
- Audio preprocessing (noise reduction)

**Month 5: Mobile & Scale**
- React Native mobile app
- Redis session storage
- Load balancing
- Horizontal scaling

**Month 6: Production Hardening**
- HIPAA compliance audit
- Security penetration testing
- Performance optimization
- Monitoring and alerting

---

**End of System Design Document**

For questions or clarifications, contact the technical team.
