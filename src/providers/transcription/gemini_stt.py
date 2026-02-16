"""
Gemini STT Provider - Audio transcription using Google Gemini API

Uses Gemini's multimodal capabilities to transcribe audio directly.
Sends audio as inline data and gets transcription via the generateContent endpoint.
No additional SDK required - uses httpx directly.
"""

import base64
import logging
import httpx
from ..base import TranscriptionProvider, TranscriptionError

logger = logging.getLogger(__name__)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiSTTProvider(TranscriptionProvider):
    """Transcription provider using Google Gemini API."""

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        self.api_key = api_key
        self.model = model
        self.client = httpx.AsyncClient(timeout=30.0)
        logger.info(f"Initialized Gemini STT provider with model: {self.model}")

    async def transcribe(self, audio_bytes: bytes) -> str:
        """
        Transcribe audio using Gemini's multimodal API.

        Args:
            audio_bytes: Raw WAV audio data

        Returns:
            Transcribed text
        """
        try:
            audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

            url = f"{GEMINI_API_URL}/{self.model}:generateContent?key={self.api_key}"

            payload = {
                "contents": [{
                    "parts": [
                        {
                            "text": (
                                "Transcribe the following audio recording exactly as spoken. "
                                "This is a medical consultation that may be in English, Hindi, or a mix of both. "
                                "Transcribe in the language that was actually spoken. "
                                "Return only the raw transcription text, no formatting, labels, or timestamps. "
                                "IMPORTANT: If the audio is silent, contains only noise, or has no intelligible speech, "
                                "respond with exactly an empty string. Do NOT invent or hallucinate any words."
                            )
                        },
                        {
                            "inline_data": {
                                "mime_type": "audio/wav",
                                "data": audio_b64
                            }
                        }
                    ]
                }],
                "generationConfig": {
                    "temperature": 0.0,
                    "maxOutputTokens": 2048
                }
            }

            response = await self.client.post(url, json=payload)

            if response.status_code != 200:
                error_text = response.text[:500]
                logger.error(f"Gemini API error {response.status_code}: {error_text}")
                raise TranscriptionError(f"Gemini API error: {response.status_code}")

            data = response.json()

            # Extract text from response
            candidates = data.get("candidates", [])
            if not candidates:
                logger.warning("Gemini returned no candidates")
                return ""

            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts:
                logger.warning("Gemini returned no parts")
                return ""

            transcript = parts[0].get("text", "").strip()
            logger.info(f"Transcription successful: {len(transcript)} characters")
            return transcript

        except TranscriptionError:
            raise
        except Exception as e:
            logger.error(f"Gemini transcription failed: {e}")
            raise TranscriptionError(f"Gemini transcription failed: {e}")
