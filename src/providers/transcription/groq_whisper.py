import logging
from io import BytesIO
from groq import AsyncGroq
from ..base import TranscriptionProvider, TranscriptionError

logger = logging.getLogger(__name__)

# Try to import pydub for audio conversion (optional)
try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False
    logger.warning("pydub not available, will send audio without conversion")


class GroqWhisperProvider(TranscriptionProvider):
    """Groq Whisper transcription provider - FREE & 5x faster than OpenAI!"""
    
    def __init__(self, api_key: str, model: str = "whisper-large-v3"):
        self.client = AsyncGroq(api_key=api_key)
        self.model = model
        logger.info(f"🚀 Initialized Groq Whisper provider with model: {model} (FREE!)")
    
    async def transcribe(self, audio_bytes: bytes) -> str:
        """Transcribe audio using Groq Whisper API."""
        try:
            logger.debug(f"Received {len(audio_bytes)} bytes of audio")

            # Detect audio format from header
            audio_format = self._detect_audio_format(audio_bytes)
            logger.debug(f"Detected audio format: {audio_format}")

            # Create file-like object with appropriate extension
            audio_file = BytesIO(audio_bytes)
            audio_file.name = f"audio.{audio_format}"

            logger.debug(f"Sending {len(audio_bytes)} bytes to Groq as {audio_file.name}")

            response = await self.client.audio.transcriptions.create(
                model=self.model,
                file=audio_file,
                response_format="text"
            )

            transcript = response.text if hasattr(response, 'text') else str(response)
            logger.info(f"✅ Transcription successful: {len(transcript)} characters")

            return transcript

        except Exception as e:
            logger.error(f"Transcription failed: {str(e)}")
            raise TranscriptionError(f"Failed to transcribe audio: {str(e)}")

    def _detect_audio_format(self, audio_bytes: bytes) -> str:
        """Detect audio format from file header."""
        if len(audio_bytes) < 12:
            return "webm"  # default fallback

        # Check magic numbers
        header = audio_bytes[:12]

        # WAV: RIFF....WAVE
        if header[:4] == b'RIFF' and header[8:12] == b'WAVE':
            return "wav"

        # WebM: 0x1A 0x45 0xDF 0xA3
        if header[:4] == b'\x1a\x45\xdf\xa3':
            return "webm"

        # MP3: ID3 or 0xFF 0xFB
        if header[:3] == b'ID3' or header[:2] == b'\xff\xfb':
            return "mp3"

        # M4A/MP4: ftyp
        if b'ftyp' in header[:12]:
            return "m4a"

        logger.warning(f"Unknown audio format, header: {header[:4].hex()}")
        return "webm"  # default fallback
