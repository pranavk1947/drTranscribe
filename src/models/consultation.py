from datetime import datetime
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field
from .patient import Patient
from .extraction import ExtractionResult


class TranscriptChunk(BaseModel):
    """A single transcript chunk with speaker and timing metadata."""
    text: str
    source: str  # "mic" or "tab"
    speaker: str  # "Doctor" or "Patient"
    timestamp: float  # seconds since session start


class ConsultationSession(BaseModel):
    """Consultation session model."""

    session_id: str = Field(..., description="Unique session identifier")
    patient: Patient = Field(..., description="Patient information")
    appointment_id: Optional[str] = Field(default=None, description="EMR appointment identifier")
    started_at: datetime = Field(default_factory=datetime.utcnow)
    transcript_chunks: List[TranscriptChunk] = Field(default_factory=list)
    extraction: ExtractionResult = Field(default_factory=ExtractionResult)

    # Audio storage tracking — separate tracks for mic (doctor) and tab (patient)
    mic_chunk_paths: List[str] = Field(default_factory=list, description="Paths to mic (doctor) audio chunks")
    tab_chunk_paths: List[str] = Field(default_factory=list, description="Paths to tab (patient) audio chunks")
    mic_chunk_count: int = Field(default=0, description="Sequential mic chunk counter")
    tab_chunk_count: int = Field(default=0, description="Sequential tab chunk counter")
    audio_saved_path: Optional[str] = Field(default=None, description="Path to final saved audio file")
    
    def add_transcript_chunk(self, chunk: TranscriptChunk) -> None:
        """Add a structured transcript chunk to the session."""
        if chunk.text.strip():
            self.transcript_chunks.append(chunk)
    
    def update_extraction(self, new_extraction: ExtractionResult) -> None:
        """Update extraction by merging with new extraction."""
        self.extraction = self.extraction.merge(new_extraction)
    
    def get_full_transcript(self) -> str:
        """Get the full transcript with clear speaker boundaries.

        Returns newline-separated lines like:
            Doctor: Good morning, how are you?
            Patient: I have a headache for 3 days.
        """
        return "\n".join(
            f"{chunk.speaker}: {chunk.text}" for chunk in self.transcript_chunks
        )

    def add_audio_chunk_path(self, chunk_path: Path, source: str = "mic") -> None:
        """Record path to saved audio chunk, separated by source."""
        if source == "tab":
            self.tab_chunk_paths.append(str(chunk_path))
        else:
            self.mic_chunk_paths.append(str(chunk_path))

    def get_mic_chunk_paths(self) -> List[Path]:
        """Get mic (doctor) audio chunk paths in order."""
        return sorted([Path(p) for p in self.mic_chunk_paths])

    def get_tab_chunk_paths(self) -> List[Path]:
        """Get tab (patient) audio chunk paths in order."""
        return sorted([Path(p) for p in self.tab_chunk_paths])

    def has_audio_chunks(self) -> bool:
        """Check if any audio chunks have been saved."""
        return bool(self.mic_chunk_paths or self.tab_chunk_paths)
    
    class Config:
        arbitrary_types_allowed = True
