import logging
from io import BytesIO
from openai import AsyncAzureOpenAI
from ..base import TranscriptionProvider, TranscriptionError

logger = logging.getLogger(__name__)


class AzureWhisperProvider(TranscriptionProvider):
    """Azure OpenAI Whisper transcription provider."""
    
    def __init__(
        self,
        api_key: str,
        endpoint: str,
        deployment: str = "whisper",
        api_version: str = "2024-08-01-preview"
    ):
        self.client = AsyncAzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=api_version
        )
        self.deployment = deployment
        logger.info(f"Initialized Azure Whisper provider with deployment: {deployment}")
    
    async def transcribe(self, audio_bytes: bytes) -> str:
        """Transcribe audio using Azure OpenAI Whisper API."""
        try:
            # Create file-like object from bytes
            audio_file = BytesIO(audio_bytes)
            audio_file.name = "audio.webm"
            
            logger.debug(f"Sending {len(audio_bytes)} bytes to Azure Whisper API")
            
            response = await self.client.audio.transcriptions.create(
                model=self.deployment,
                file=audio_file,
                response_format="text"
            )
            
            transcript = response if isinstance(response, str) else response.text
            logger.info(f"Transcription successful: {len(transcript)} characters")
            
            return transcript
            
        except Exception as e:
            logger.error(f"Transcription failed: {str(e)}")
            raise TranscriptionError(f"Failed to transcribe audio: {str(e)}")
