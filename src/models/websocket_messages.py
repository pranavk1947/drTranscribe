from typing import Literal
from pydantic import BaseModel, Field
from .patient import Patient
from .extraction import ExtractionResult


class StartSessionMessage(BaseModel):
    """Message to start a new consultation session."""
    
    type: Literal["start_session"] = "start_session"
    patient: Patient


class AudioChunkMessage(BaseModel):
    """Message containing audio chunk data."""
    
    type: Literal["audio_chunk"] = "audio_chunk"
    audio_data: str = Field(..., description="Base64 encoded audio data")


class StopSessionMessage(BaseModel):
    """Message to stop the current session."""
    
    type: Literal["stop_session"] = "stop_session"


class ExtractionUpdateMessage(BaseModel):
    """Message with updated extraction results."""
    
    type: Literal["extraction_update"] = "extraction_update"
    extraction: ExtractionResult


class ErrorMessage(BaseModel):
    """Error message."""
    
    type: Literal["error"] = "error"
    message: str
