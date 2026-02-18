import json
import logging
from typing import Optional
from anthropic import AsyncAnthropic
from ..base import ExtractionProvider, ExtractionError
from ...models.extraction import ExtractionResult
from ...models.patient import Patient
from .prompts import MEDICAL_EXTRACTION_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class ClaudeGPTProvider(ExtractionProvider):
    """Claude (Anthropic) extraction provider."""



    def __init__(
        self,
        api_key: str,
        model: str = "claude-3-5-sonnet-20240620",
        temperature: float = 0.3,
        max_tokens: int = 1024
    ):
        self.client = AsyncAnthropic(api_key=api_key)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        logger.info(f"Initialized Claude provider with model: {model}")

    async def extract(
        self,
        transcript: str,
        patient: Patient,
        previous_extraction: Optional[ExtractionResult] = None
    ) -> ExtractionResult:
        """Extract structured data using Claude API."""
        try:
            user_prompt = self._build_user_prompt(transcript, patient, previous_extraction)

            logger.debug(f"Sending extraction request for {len(transcript)} chars")

            response = await self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=MEDICAL_EXTRACTION_SYSTEM_PROMPT,
                messages=[
                    {"role": "user", "content": user_prompt}
                ]
            )

            # Extract JSON from response
            content = response.content[0].text

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
