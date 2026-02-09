from datetime import datetime
from typing import List
from pydantic import BaseModel, Field
from .patient import Patient
from .extraction import ExtractionResult


class ConsultationSession(BaseModel):
    """Consultation session model."""
    
    session_id: str = Field(..., description="Unique session identifier")
    patient: Patient = Field(..., description="Patient information")
    started_at: datetime = Field(default_factory=datetime.utcnow)
    transcript_chunks: List[str] = Field(default_factory=list)
    extraction: ExtractionResult = Field(default_factory=ExtractionResult)
    
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
    
    class Config:
        arbitrary_types_allowed = True
