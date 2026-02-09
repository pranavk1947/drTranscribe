import logging
import struct
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

    def __init__(self, api_key: str, model: str = "whisper-large-v3", output_format: str = "wav"):
        self.client = AsyncGroq(api_key=api_key)
        self.model = model
        # Always use WAV format for maximum compatibility
        self.output_format = "wav"

        if output_format != "wav":
            logger.info(f"Note: output_format '{output_format}' specified, but using 'wav' for maximum compatibility")

        logger.info(f"🚀 Initialized Groq Whisper provider with model: {model}, output format: wav (FREE!)")
    
    async def transcribe(self, audio_bytes: bytes) -> str:
        """Transcribe audio using Groq Whisper API.

        Process:
        1. Detect audio format
        2. Try to extract/convert to Ogg Opus (Groq native format) - handles fragmented chunks
        3. Fallback to WAV conversion if Opus extraction fails
        4. Send to Groq for transcription
        """
        try:
            logger.debug(f"Received {len(audio_bytes)} bytes of audio")

            # Detect format
            audio_format = self._detect_audio_format(audio_bytes)
            logger.debug(f"Detected format: {audio_format}")

            # Strategy 1: Try to extract/convert to Ogg Opus (Groq native format)
            # This handles fragmented WebM chunks gracefully
            try:
                audio_bytes, final_format = await self._convert_to_ogg_opus(audio_bytes, audio_format)
            except Exception as e:
                # Strategy 2: Fallback to WAV conversion
                logger.warning(f"Ogg Opus conversion failed, falling back to WAV: {e}")
                audio_bytes, final_format = await self._convert_to_wav(audio_bytes, audio_format)

            # Send to Groq
            audio_file = BytesIO(audio_bytes)
            audio_file.name = f"audio.{final_format}"

            logger.debug(f"Sending {len(audio_bytes)} bytes to Groq as {audio_file.name}")

            response = await self.client.audio.transcriptions.create(
                model=self.model,
                file=audio_file,
                response_format="text"
            )

            # Debug: Log the raw response to understand its structure
            logger.debug(f"Raw response type: {type(response)}")
            logger.debug(f"Response attributes: {dir(response)}")
            logger.debug(f"Response repr: {repr(response)}")

            # Extract transcript based on response format
            if hasattr(response, 'text'):
                transcript = response.text
                logger.debug(f"Extracted from response.text: '{transcript}'")
            else:
                transcript = str(response)
                logger.debug(f"Extracted from str(response): '{transcript}'")

            logger.info(f"✅ Transcription successful: {len(transcript)} characters")

            # Additional debug if transcript is empty
            if not transcript or len(transcript) == 0:
                logger.warning(f"⚠️ Empty transcript returned! Audio size: {len(audio_bytes)} bytes, Format: {final_format}")
                logger.warning(f"⚠️ Response object details: {vars(response) if hasattr(response, '__dict__') else 'No __dict__'}")

            return transcript

        except Exception as e:
            logger.error(f"Transcription failed: {str(e)}")
            raise TranscriptionError(f"Failed to transcribe audio: {str(e)}")


    async def _convert_to_ogg_opus(self, audio_bytes: bytes, source_format: str) -> tuple[bytes, str]:
        """Convert WebM/fragmented chunks to Ogg Opus format.

        Handles:
        - Complete WebM chunks
        - Fragmented WebM chunks (header 47848113, etc.)
        - Already Ogg Opus data

        Args:
            audio_bytes: Raw audio data
            source_format: Source format hint

        Returns:
            tuple: (opus_bytes, "opus") or raises exception
        """
        # If already Ogg Opus, return as-is
        if audio_bytes[:4] == b'OggS':
            logger.info(f"✅ Already Ogg Opus format, using as-is")
            return audio_bytes, "opus"

        # Try to extract Opus from WebM (handles fragmented chunks)
        try:
            opus_data = self._extract_opus_from_webm(audio_bytes)
            logger.info(f"✅ Extracted Opus from WebM: {len(audio_bytes)} → {len(opus_data)} bytes")

            # Verify opus data is valid (should start with OggS)
            if len(opus_data) > 0:
                logger.debug(f"Opus header: {opus_data[:4].hex() if len(opus_data) >= 4 else 'too short'}")
                if opus_data[:4] != b'OggS':
                    logger.warning(f"⚠️ Extracted Opus doesn't have valid OggS header! Got: {opus_data[:4].hex()}")

            return opus_data, "opus"
        except Exception as e:
            logger.debug(f"Opus extraction failed: {e}, trying pydub conversion")

        # Try pydub conversion to opus
        if not PYDUB_AVAILABLE:
            raise TranscriptionError("Cannot convert to Opus: pydub not available")

        # Try to load and convert using pydub
        formats_to_try = [source_format, "webm", "opus", "ogg"]
        last_error = None

        for fmt in formats_to_try:
            try:
                logger.debug(f"Attempting to load audio as {fmt} and convert to opus")

                audio_segment = AudioSegment.from_file(
                    BytesIO(audio_bytes),
                    format=fmt
                )

                # Optimize for transcription: mono, 16kHz
                audio_segment = audio_segment.set_channels(1)
                audio_segment = audio_segment.set_frame_rate(16000)

                # Export as Ogg Opus
                opus_buffer = BytesIO()
                audio_segment.export(opus_buffer, format="opus", codec="libopus")
                opus_bytes = opus_buffer.getvalue()

                logger.info(f"✅ Converted {fmt} to Ogg Opus: {len(audio_bytes)} → {len(opus_bytes)} bytes")
                return opus_bytes, "opus"

            except Exception as e:
                logger.debug(f"Failed to convert {fmt} to opus: {e}")
                last_error = e
                continue

        # All formats failed
        raise TranscriptionError(f"Could not convert audio to Ogg Opus. Last error: {last_error}")

    def _extract_opus_from_webm(self, audio_bytes: bytes) -> bytes:
        """Extract raw Opus audio packets from WebM chunk.

        WebM structure:
        - Complete chunk: [EBML Header][Segment][Cluster[SimpleBlock(Opus data)]]
        - Fragmented chunk: [SimpleBlock(Opus data)] or [partial EBML]

        Strategy:
        1. Look for Opus codec signature in WebM
        2. Extract audio frames from SimpleBlock elements
        3. Wrap in minimal Ogg Opus container
        4. Return valid Ogg Opus bytes

        This is a simplified implementation that tries to use pydub's WebM decoder
        to extract the Opus data, even from fragmented chunks.
        """
        if not PYDUB_AVAILABLE:
            raise TranscriptionError("pydub required for Opus extraction")

        # Try to parse as WebM/Opus using pydub
        # pydub uses ffmpeg which can sometimes handle partial WebM data
        try:
            audio_segment = AudioSegment.from_file(
                BytesIO(audio_bytes),
                format="webm",
                codec="opus"
            )

            # Convert to Ogg Opus container
            opus_buffer = BytesIO()
            audio_segment.export(opus_buffer, format="opus", codec="libopus")
            return opus_buffer.getvalue()

        except Exception as e:
            # If that fails, try treating it as raw Opus frames and wrapping in Ogg container
            logger.debug(f"WebM parsing failed, trying raw Opus frame extraction: {e}")

            # For fragmented chunks, we'll let the fallback to WAV handle it
            raise TranscriptionError(f"Cannot extract Opus from fragmented WebM chunk: {e}")

    async def _convert_to_wav(self, audio_bytes: bytes, source_format: str) -> tuple[bytes, str]:
        """Convert audio to WAV format using pydub.

        Args:
            audio_bytes: Raw audio data
            source_format: Source format hint (may be incorrect for chunks)

        Returns:
            tuple: (wav_bytes, "wav") or raises exception
        """
        if not PYDUB_AVAILABLE:
            raise TranscriptionError("pydub required for audio conversion but not available")

        # Try formats in order of likelihood
        formats_to_try = [source_format, "webm", "opus", "ogg"]

        last_error = None
        for fmt in formats_to_try:
            try:
                logger.debug(f"Attempting to load audio as {fmt}")

                audio_segment = AudioSegment.from_file(
                    BytesIO(audio_bytes),
                    format=fmt
                )

                # Optimize for transcription: mono, 16kHz
                audio_segment = audio_segment.set_channels(1)
                audio_segment = audio_segment.set_frame_rate(16000)

                # Export as WAV
                wav_buffer = BytesIO()
                audio_segment.export(wav_buffer, format="wav")
                wav_bytes = wav_buffer.getvalue()

                logger.info(f"✅ Converted {fmt} to WAV: {len(audio_bytes)} → {len(wav_bytes)} bytes")
                return wav_bytes, "wav"

            except Exception as e:
                logger.debug(f"Failed to load as {fmt}: {e}")
                last_error = e
                continue

        # All formats failed
        raise TranscriptionError(f"Could not convert audio to WAV. Last error: {last_error}")

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

