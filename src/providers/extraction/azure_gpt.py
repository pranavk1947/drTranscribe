import json
import logging
from typing import Optional
from openai import AsyncAzureOpenAI
from ..base import ExtractionProvider, ExtractionError
from ...models.extraction import ExtractionResult
from ...models.patient import Patient
from .prompts import MEDICAL_EXTRACTION_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class AzureGPTProvider(ExtractionProvider):
    """Azure OpenAI GPT extraction provider."""

    def __init__(
        self,
        api_key: str,
        endpoint: str,
        deployment: str,
        api_version: str = "2024-08-01-preview",
        temperature: float = 0.3
    ):
        self.client = AsyncAzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=api_version
        )
        self.deployment = deployment
        self.temperature = temperature
        logger.info(f"Initialized Azure GPT provider with deployment: {deployment}")
    
    async def extract(
        self,
        transcript: str,
        patient: Patient,
        previous_extraction: Optional[ExtractionResult] = None
    ) -> ExtractionResult:
        """Extract structured data using Azure OpenAI GPT API."""
        try:
            user_prompt = self._build_user_prompt(transcript, patient, previous_extraction)
            
            logger.debug(f"Sending extraction request for {len(transcript)} chars")
            
            response = await self.client.chat.completions.create(
                model=self.deployment,
                messages=[
                    {"role": "system", "content": MEDICAL_EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=self.temperature,
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            extraction_data = json.loads(content)
            
            result = ExtractionResult(**extraction_data)
            logger.info(f"Extraction successful")
            
            return result
            
        except Exception as e:
            logger.error(f"Extraction failed: {str(e)}")
            raise ExtractionError(f"Failed to extract clinical data: {str(e)}")
    
    def _build_user_prompt(
        self,
        transcript: str,
        patient: Patient,
        previous_extraction: Optional[ExtractionResult]
    ) -> str:
        """Build the user prompt for extraction."""
        prompt = f"""Patient Information:
- Name: {patient.name}
- Age: {patient.age}
- Gender: {patient.gender}

Transcript:
{transcript}

Note: The transcript may contain Hindi or mixed Hindi-English speech. Extract and write all fields in English only."""
        
        if previous_extraction:
            prompt += f"""

Previous Extraction (merge with this):
{previous_extraction.model_dump_json(indent=2)}"""
        
        return prompt
