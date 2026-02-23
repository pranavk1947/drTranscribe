import json
import logging
from typing import Optional
from google import genai
from google.genai import types
from ..base import ExtractionProvider, ExtractionError
from ...models.extraction import ExtractionResult
from ...models.patient import Patient
from .prompts import MEDICAL_EXTRACTION_SYSTEM_PROMPT, MEDICAL_EXTRACTION_MERGE_INSTRUCTIONS

logger = logging.getLogger(__name__)


class GeminiGPTProvider(ExtractionProvider):
    """Google Gemini extraction provider using the google-genai SDK."""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash",
        temperature: float = 0.3
    ):
        self.client = genai.Client(api_key=api_key)
        self.model_name = model
        self.temperature = temperature
        logger.info(f"Initialized Gemini provider with model: {model}")

    async def extract(
        self,
        transcript: str,
        patient: Patient,
        previous_extraction: Optional[ExtractionResult] = None
    ) -> ExtractionResult:
        """Extract structured data using Gemini API."""
        try:
            user_prompt = self._build_user_prompt(transcript, patient, previous_extraction)

            logger.debug(f"Sending extraction request for {len(transcript)} chars")

            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=MEDICAL_EXTRACTION_SYSTEM_PROMPT,
                    temperature=self.temperature,
                    response_mime_type="application/json",
                    response_schema=ExtractionResult,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )

            extraction_data = json.loads(response.text)
            result = ExtractionResult(**extraction_data)
            logger.info("Extraction successful")

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
        """Build the user prompt with context first, instructions last."""
        parts = []

        # Context first: patient info
        patient_info = f"<patient>\nName: {patient.name}\nAge: {patient.age}\nGender: {patient.gender}"
        if patient.history:
            patient_info += f"\nMedical History: {patient.history}"
        patient_info += "\n</patient>"
        parts.append(patient_info)

        # Context: transcript
        parts.append(f"<transcript>\n{transcript}\n</transcript>")

        # Context: previous extraction (if any)
        if previous_extraction:
            parts.append(
                f"<previous_extraction>\n{previous_extraction.model_dump_json(indent=2)}\n</previous_extraction>"
            )
            # Instructions last
            parts.append(MEDICAL_EXTRACTION_MERGE_INSTRUCTIONS)

        parts.append("Extract the structured clinical data from the transcript above.")

        return "\n\n".join(parts)
