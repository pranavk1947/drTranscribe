import json
import logging
from typing import Optional
from openai import AsyncOpenAI
from ..base import ExtractionProvider, ExtractionError
from ...models.extraction import ExtractionResult
from ...models.patient import Patient
from .prompts import MEDICAL_EXTRACTION_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class OpenAIGPTProvider(ExtractionProvider):
    """OpenAI GPT extraction provider."""
    
    def __init__(self, api_key: str, model: str = "gpt-4", temperature: float = 0.3):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self.temperature = temperature
        logger.info(f"Initialized OpenAI GPT provider with model: {model}")
    
    async def extract(
        self,
        transcript: str,
        patient: Patient,
        previous_extraction: Optional[ExtractionResult] = None
    ) -> ExtractionResult:
        """Extract structured data using OpenAI GPT API."""
        try:
            user_prompt = self._build_user_prompt(transcript, patient, previous_extraction)
            
            logger.debug(f"Sending extraction request for {len(transcript)} chars")
            
            response = await self.client.chat.completions.create(
                model=self.model,
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
{transcript}"""
        
        if previous_extraction:
            prompt += f"""

Previous Extraction (merge with this):
{previous_extraction.model_dump_json(indent=2)}"""
        
        return prompt
