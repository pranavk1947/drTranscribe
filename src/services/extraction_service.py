import logging
from typing import Dict, Type, Optional
from ..providers.base import ExtractionProvider
from ..providers.extraction.openai_gpt import OpenAIGPTProvider
from ..providers.extraction.azure_gpt import AzureGPTProvider
from ..providers.extraction.claude_gpt import ClaudeGPTProvider
from ..providers.extraction.gemini_gpt import GeminiGPTProvider
from ..providers.extraction.groq_gpt import GroqGPTProvider
from ..providers.extraction.mock_gpt import MockGPTProvider
from ..models.patient import Patient
from ..models.extraction import ExtractionResult
from ..config.settings import Settings

logger = logging.getLogger(__name__)


class ExtractionService:
    """Extraction service with provider abstraction."""

    PROVIDERS: Dict[str, Type[ExtractionProvider]] = {
        "openai": OpenAIGPTProvider,
        "azure": AzureGPTProvider,
        "claude": ClaudeGPTProvider,
        "gemini": GeminiGPTProvider,
        "groq": GroqGPTProvider,
        "mock": MockGPTProvider,
    }

    def __init__(self, settings: Settings):
        self.settings = settings
        self.provider = self._create_provider()

    def _create_provider(self) -> ExtractionProvider:
        """Factory method to create extraction provider from config."""
        provider_name = self.settings.extraction.provider

        if provider_name not in self.PROVIDERS:
            raise ValueError(f"Unknown extraction provider: {provider_name}")

        provider_class = self.PROVIDERS[provider_name]

        if provider_name == "openai":
            if not self.settings.openai:
                raise ValueError("OpenAI configuration not found")
            return provider_class(
                api_key=self.settings.openai.api_key,
                model=self.settings.extraction.model,
                temperature=self.settings.extraction.temperature
            )

        elif provider_name == "azure":
            if not self.settings.azure_openai:
                raise ValueError("Azure OpenAI configuration not found")
            return provider_class(
                api_key=self.settings.azure_openai.api_key,
                endpoint=self.settings.azure_openai.endpoint,
                deployment=self.settings.azure_openai.gpt_deployment,
                api_version=self.settings.azure_openai.api_version,
                temperature=self.settings.extraction.temperature
            )

        elif provider_name == "claude":
            if not self.settings.claude:
                raise ValueError("Claude configuration not found")
            return provider_class(
                api_key=self.settings.claude.api_key,
                model=self.settings.extraction.model,
                temperature=self.settings.extraction.temperature
            )

        elif provider_name == "gemini":
            if not self.settings.gemini:
                raise ValueError("Gemini configuration not found")
            return provider_class(
                api_key=self.settings.gemini.api_key,
                model=self.settings.extraction.model,
                temperature=self.settings.extraction.temperature
            )

        elif provider_name == "groq":
            if not self.settings.groq:
                raise ValueError("Groq configuration not found")
            return provider_class(
                api_key=self.settings.groq.api_key,
                model=self.settings.extraction.model,
                temperature=self.settings.extraction.temperature
            )

        elif provider_name == "mock":
            return provider_class()

        raise ValueError(f"Provider initialization not implemented: {provider_name}")
    
    async def extract(
        self,
        transcript: str,
        patient: Patient,
        previous_extraction: Optional[ExtractionResult] = None
    ) -> ExtractionResult:
        """Extract structured clinical data from transcript."""
        return await self.provider.extract(transcript, patient, previous_extraction)
