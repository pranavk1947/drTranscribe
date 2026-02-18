import json
import logging
from typing import Optional
import google.generativeai as genai
from ..base import ExtractionProvider, ExtractionError
from ...models.extraction import ExtractionResult
from ...models.patient import Patient
from .prompts import MEDICAL_EXTRACTION_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class GeminiGPTProvider(ExtractionProvider):
    """Google Gemini extraction provider."""



    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash",
        temperature: float = 0.3
    ):
        genai.configure(api_key=api_key)

        # Gemini 1.5+ supports JSON response format
        generation_config = {
            "temperature": temperature,
            "response_mime_type": "application/json"
        }

        self.model = genai.GenerativeModel(
            model_name=model,
            generation_config=generation_config
        )
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
            full_prompt = f"{MEDICAL_EXTRACTION_SYSTEM_PROMPT}\n\n{user_prompt}"

            logger.debug(f"Sending extraction request for {len(transcript)} chars")

            # Gemini SDK is synchronous, but we can use it in async context
            response = self.model.generate_content(full_prompt)

            # Extract JSON from response
            content = response.text

            # Try to parse JSON directly
            try:
                extraction_data = json.loads(content)
            except json.JSONDecodeError:
                # If not valid JSON, try to extract JSON from markdown code block
                if "```json" in content:
                    json_str = content.split("```json")[1].split("```")[0].strip()
                    extraction_data = json.loads(json_str)
                elif "```" in content:
                    json_str = content.split("```")[1].split("```")[0].strip()
                    extraction_data = json.loads(json_str)
                else:
                    raise ValueError("Response is not valid JSON")

            result = ExtractionResult(**extraction_data)
            logger.info(f"✅ Extraction successful")

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
        prompt = f"""**Patient Information:**
- Name: {patient.name}
- Age: {patient.age}
- Gender: {patient.gender}"""

        if patient.history:
            prompt += f"\n- Medical History: {patient.history}"

        prompt += f"""

**Current Transcript:**
{transcript}"""

        if previous_extraction:
            prompt += f"""

**Previous Extraction (merge new info with this):**
```json
{previous_extraction.model_dump_json(indent=2)}
```

IMPORTANT: Merge the current transcript information with the previous extraction. Add new information, don't replace existing valid data unless there's a correction."""

        prompt += """

Return the complete extraction as valid JSON with all 5 fields."""

        return prompt
