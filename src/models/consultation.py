from datetime import datetime
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field
from .patient import Patient
from .extraction import ExtractionResult


class ConsultationSession(BaseModel):
    """Consultation session model."""

    session_id: str = Field(..., description="Unique session identifier")
    patient: Patient = Field(..., description="Patient information")
    appointment_id: Optional[str] = Field(default=None, description="EMR appointment identifier")
    started_at: datetime = Field(default_factory=datetime.utcnow)
    transcript_chunks: List[str] = Field(default_factory=list)
    extraction: ExtractionResult = Field(default_factory=ExtractionResult)

    # Audio storage tracking
    audio_chunk_paths: List[str] = Field(default_factory=list, description="Paths to saved audio chunks")
    audio_chunk_count: int = Field(default=0, description="Sequential chunk counter")
    audio_saved_path: Optional[str] = Field(default=None, description="Path to final saved audio file")
    
    def add_transcript_chunk(self, chunk: str) -> None:
        """Add a transcript chunk to the session."""
        if chunk:
            self.transcript_chunks.append(chunk)
    
    def update_extraction(self, new_extraction: ExtractionResult) -> None:
        """Update extraction by merging with new extraction."""
        self.extraction = self.extraction.merge(new_extraction)
    
    def get_full_transcript(self) -> str:
        """Get the full transcript from all chunks."""
        return " ".join(self.transcript_chunks)

    def add_audio_chunk_path(self, chunk_path: Path) -> None:
        """Record path to saved audio chunk."""
        self.audio_chunk_paths.append(str(chunk_path))

    def get_audio_chunk_paths(self) -> List[Path]:
        """Get list of audio chunk paths."""
        return [Path(p) for p in self.audio_chunk_paths]
    
    class Config:
        arbitrary_types_allowed = True
