import logging
from pathlib import Path
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from .config.settings import load_settings
from .services.transcription_service import TranscriptionService
from .services.extraction_service import ExtractionService
from .services.session_manager import SessionManager
from .services.audio_storage import AudioStorageService
from .websocket_handler import WebSocketHandler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/medlog.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Load settings
settings = load_settings()

# Create FastAPI app
app = FastAPI(title="MedLog", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
transcription_service = TranscriptionService(settings)
extraction_service = ExtractionService(settings)
session_manager = SessionManager()
audio_storage_service = AudioStorageService(settings)

# Initialize WebSocket handler
ws_handler = WebSocketHandler(
    settings=settings,
    transcription_service=transcription_service,
    extraction_service=extraction_service,
    session_manager=session_manager,
    audio_storage_service=audio_storage_service
)

# Serve frontend static files (includes AudioWorklet processor, audio-recorder.js, wav-encoder.js)
frontend_dir = Path(__file__).parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=frontend_dir), name="static")


@app.get("/")
async def root():
    """Serve the frontend."""
    return FileResponse(frontend_dir / "index.html")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "active_sessions": session_manager.get_active_sessions_count()
    }


@app.get("/api/config")
async def get_frontend_config():
    """
    Provide frontend configuration for audio capture.

    Returns audio settings needed by AudioWorklet:
    - chunk_duration_seconds: Duration of each audio chunk
    - sample_rate: Audio sample rate in Hz
    - channels: Number of audio channels (1=mono, 2=stereo)
    """
    return {
        "audio": {
            "chunk_duration_seconds": settings.audio.chunk_duration_seconds,
            "sample_rate": settings.audio.sample_rate,
            "channels": settings.audio.channels
        }
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time transcription."""
    await ws_handler.handle_connection(websocket)


if __name__ == "__main__":
    import uvicorn
    
    logger.info("Starting MedLog server")
    logger.info(f"Transcription provider: {settings.transcription.provider}")
    logger.info(f"Extraction provider: {settings.extraction.provider}")
    
    uvicorn.run(
        app,
        host=settings.server.host,
        port=settings.server.port,
        log_level="info"
    )
