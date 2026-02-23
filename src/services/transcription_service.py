import logging
from typing import Dict, Type
from ..providers.base import TranscriptionProvider
from ..providers.transcription.openai_whisper import OpenAIWhisperProvider
from ..providers.transcription.azure_whisper import AzureWhisperProvider
from ..providers.transcription.groq_whisper import GroqWhisperProvider
from ..providers.transcription.gemini_stt import GeminiSTTProvider
from ..providers.transcription.google_stt import GoogleSTTProvider
from ..providers.transcription.mock_whisper import MockWhisperProvider
from ..config.settings import Settings

logger = logging.getLogger(__name__)


class TranscriptionService:
    """Transcription service with provider abstraction."""

    PROVIDERS: Dict[str, Type[TranscriptionProvider]] = {
        "openai": OpenAIWhisperProvider,
        "azure": AzureWhisperProvider,
        "groq": GroqWhisperProvider,
        "gemini": GeminiSTTProvider,
        "google_stt": GoogleSTTProvider,
        "mock": MockWhisperProvider,
    }

    def __init__(self, settings: Settings):
        self.settings = settings
        self.provider = self._create_provider()

    def _create_provider(self) -> TranscriptionProvider:
        """Factory method to create transcription provider from config."""
        provider_name = self.settings.transcription.provider

        if provider_name not in self.PROVIDERS:
            raise ValueError(f"Unknown transcription provider: {provider_name}")

        provider_class = self.PROVIDERS[provider_name]

        if provider_name == "openai":
            if not self.settings.openai:
                raise ValueError("OpenAI configuration not found")
            return provider_class(
                api_key=self.settings.openai.api_key,
                model=self.settings.transcription.model
            )

        elif provider_name == "azure":
            if not self.settings.azure_openai:
                raise ValueError("Azure OpenAI configuration not found")
            return provider_class(
                api_key=self.settings.azure_openai.api_key,
                endpoint=self.settings.azure_openai.endpoint,
                deployment=self.settings.azure_openai.whisper_deployment,
                api_version=self.settings.azure_openai.api_version
            )

        elif provider_name == "groq":
            if not self.settings.groq:
                raise ValueError("Groq configuration not found")
            return provider_class(
                api_key=self.settings.groq.api_key,
                model=self.settings.transcription.model,
                output_format=self.settings.transcription.output_format
            )

        elif provider_name == "gemini":
            if not self.settings.gemini:
                raise ValueError("Gemini configuration not found")
            return provider_class(
                api_key=self.settings.gemini.api_key,
                model=self.settings.transcription.model
            )

        elif provider_name == "google_stt":
            if not self.settings.gemini:
                raise ValueError("Gemini/Google configuration not found (google_stt uses gemini.api_key)")
            return provider_class(
                api_key=self.settings.gemini.api_key,
                model=self.settings.transcription.model,
                sample_rate=self.settings.audio.sample_rate
            )

        elif provider_name == "mock":
            return provider_class()

        raise ValueError(f"Provider initialization not implemented: {provider_name}")
    
    async def transcribe(self, audio_bytes: bytes) -> str:
        """Transcribe audio bytes to text."""
        return await self.provider.transcribe(audio_bytes)
