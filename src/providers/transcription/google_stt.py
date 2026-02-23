"""
Google Cloud Speech-to-Text Provider

Uses the Google Cloud Speech-to-Text REST API for audio transcription.
This is a dedicated STT service (not an LLM), so it does not hallucinate.
Accepts WAV LINEAR16 directly - no format conversion needed.
Uses httpx for HTTP requests - no additional SDK required.
"""

import base64
import logging
import httpx
from ..base import TranscriptionProvider, TranscriptionError

logger = logging.getLogger(__name__)

GOOGLE_STT_API_URL = "https://speech.googleapis.com/v1/speech:recognize"


class GoogleSTTProvider(TranscriptionProvider):
    """Transcription provider using Google Cloud Speech-to-Text API."""

    def __init__(self, api_key: str, model: str = "default", sample_rate: int = 16000):
        self.api_key = api_key
        self.model = model
        self.sample_rate = sample_rate
        self.client = httpx.AsyncClient(timeout=30.0)
        logger.info(f"Initialized Google Cloud STT provider (sample_rate={sample_rate}Hz)")

    async def transcribe(self, audio_bytes: bytes) -> str:
        """
        Transcribe audio using Google Cloud Speech-to-Text API.

        Args:
            audio_bytes: Raw WAV audio data (LINEAR16, 16kHz, mono)

        Returns:
            Transcribed text
        """
        try:
            # Strip WAV header (44 bytes) and send raw PCM
            # Google STT expects raw LINEAR16 when encoding is specified
            if len(audio_bytes) > 44 and audio_bytes[:4] == b'RIFF':
                pcm_data = audio_bytes[44:]
            else:
                pcm_data = audio_bytes

            audio_b64 = base64.b64encode(pcm_data).decode("utf-8")

            url = f"{GOOGLE_STT_API_URL}?key={self.api_key}"

            payload = {
                "config": {
                    "encoding": "LINEAR16",
                    "sampleRateHertz": self.sample_rate,
                    "languageCode": "en-IN",
                    "alternativeLanguageCodes": ["hi-IN"],
                    "enableAutomaticPunctuation": True,
                    "model": self.model if self.model != "default" else "default",
                },
                "audio": {
                    "content": audio_b64
                }
            }

            response = await self.client.post(url, json=payload)

            if response.status_code != 200:
                error_text = response.text[:500]
                logger.error(f"Google STT API error {response.status_code}: {error_text}")
                raise TranscriptionError(f"Google STT API error: {response.status_code}")

            data = response.json()

            # Extract transcript from response
            results = data.get("results", [])
            if not results:
                logger.debug("Google STT returned no results (likely silence)")
                return ""

            # Concatenate all result transcripts
            transcript_parts = []
            for result in results:
                alternatives = result.get("alternatives", [])
                if alternatives:
                    text = alternatives[0].get("transcript", "")
                    if text:
                        transcript_parts.append(text)

            transcript = " ".join(transcript_parts).strip()
            logger.info(f"Transcription successful: {len(transcript)} characters")
            return transcript

        except TranscriptionError:
            raise
        except Exception as e:
            logger.error(f"Google STT transcription failed: {e}")
            raise TranscriptionError(f"Google STT transcription failed: {e}")
