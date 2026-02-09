import logging
from io import BytesIO
from openai import AsyncOpenAI
from ..base import TranscriptionProvider, TranscriptionError

logger = logging.getLogger(__name__)


class OpenAIWhisperProvider(TranscriptionProvider):
    """OpenAI Whisper transcription provider."""
    
    def __init__(self, api_key: str, model: str = "whisper-1"):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        logger.info(f"Initialized OpenAI Whisper provider with model: {model}")
    
    async def transcribe(self, audio_bytes: bytes) -> str:
        """Transcribe audio using OpenAI Whisper API."""
        try:
            # Create file-like object from bytes
            audio_file = BytesIO(audio_bytes)
            audio_file.name = "audio.webm"  # Required by OpenAI API
            
            logger.debug(f"Sending {len(audio_bytes)} bytes to Whisper API")
            
            response = await self.client.audio.transcriptions.create(
                model=self.model,
                file=audio_file,
                response_format="text"
            )
            
            transcript = response if isinstance(response, str) else response.text
            logger.info(f"Transcription successful: {len(transcript)} characters")
            
            return transcript
            
        except Exception as e:
            logger.error(f"Transcription failed: {str(e)}")
            raise TranscriptionError(f"Failed to transcribe audio: {str(e)}")
