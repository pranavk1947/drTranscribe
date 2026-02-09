from abc import ABC, abstractmethod
from typing import Optional
from ..models.extraction import ExtractionResult
from ..models.patient import Patient


class TranscriptionProvider(ABC):
    """Abstract base class for transcription providers."""
    
    @abstractmethod
    async def transcribe(self, audio_bytes: bytes) -> str:
        """
        Transcribe audio bytes to text.
        
        Args:
            audio_bytes: Raw audio data
            
        Returns:
            Transcribed text
        """
        pass


class ExtractionProvider(ABC):
    """Abstract base class for extraction providers."""
    
    @abstractmethod
    async def extract(
        self,
        transcript: str,
        patient: Patient,
        previous_extraction: Optional[ExtractionResult] = None
    ) -> ExtractionResult:
        """
        Extract structured clinical data from transcript.
        
        Args:
            transcript: Full transcript text
            patient: Patient information
            previous_extraction: Previous extraction result to merge with
            
        Returns:
            Extracted clinical data
        """
        pass


class TranscriptionError(Exception):
    """Exception raised when transcription fails."""
    pass


class ExtractionError(Exception):
    """Exception raised when extraction fails."""
    pass
