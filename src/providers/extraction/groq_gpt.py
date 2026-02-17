import json
import logging
from typing import Optional
from groq import AsyncGroq
from ..base import ExtractionProvider, ExtractionError
from ...models.extraction import ExtractionResult
from ...models.patient import Patient

logger = logging.getLogger(__name__)


class GroqGPTProvider(ExtractionProvider):
    """Groq Llama extraction provider (FREE!)."""

    SYSTEM_PROMPT = """You are a medical transcription assistant. Your role is to EXTRACT and STRUCTURE what was actually said - NOT to suggest, recommend, or predict anything.

**LANGUAGE: The transcript may be in Hindi, English, or a mix of both (code-switching is common in Indian medical consultations). Regardless of the transcript language, ALL extracted fields MUST be written in English. Translate any Hindi content to English.**

⚠️ MEDICAL SAFETY CRITICAL ⚠️
You are NOT a medical assistant. You are a TRANSCRIPTION assistant.
ONLY write down what the doctor EXPLICITLY SAID.
NEVER suggest treatments, medicines, or advice on your own.

Extract into these 5 sections:
1. Chief Complaint: Patient's primary reason for visit (ONLY what patient stated)
2. Diagnosis: Doctor's assessment (ONLY if doctor explicitly stated)
3. Medicine: Medications prescribed with dosage (ONLY if doctor explicitly prescribed)
4. Advice: Lifestyle advice (ONLY if doctor explicitly gave advice)
5. Next Steps: Lab tests, follow-up, cross-consultation (ONLY if doctor explicitly mentioned)

**CRITICAL: Strict Extraction Rules**
- ONLY extract information that is EXPLICITLY STATED in the transcript
- NEVER infer, guess, predict, assume, or suggest information
- NEVER add "common sense" medical recommendations
- If the doctor has NOT mentioned a field yet, return an EMPTY STRING "" for that field
- Medical accuracy requires ZERO hallucination, ZERO prediction, ZERO suggestions
- When in doubt, leave the field EMPTY

**CRITICAL: Format Requirements**
- Return valid JSON with exact keys: chief_complaint, diagnosis, medicine, advice, next_steps
- ALL field values MUST be single strings, NOT arrays or lists
- If multiple pieces of information exist for a field, combine them into ONE string separated by semicolons
- Example: {"medicine": "Ibuprofen 400mg twice daily; Vitamin B complex once daily"}
- Example EMPTY field: {"medicine": ""}

**CRITICAL: Merging Instructions (when previous extraction provided)**
- For each field, ADD new info to existing info (if any)
- NEVER remove or replace existing valid information
- NEVER repeat the same information twice
- If current chunk contradicts previous, REPLACE with new value
- Separate multiple items with semicolons

Return ONLY valid JSON with all 5 fields."""

    def __init__(
        self,
        api_key: str,
        model: str = "llama-3.3-70b-versatile",
        temperature: float = 0.3
    ):
        self.client = AsyncGroq(api_key=api_key)
        self.model = model
        self.temperature = temperature
        logger.info(f"Initialized Groq provider with model: {model}")

    async def extract(
        self,
        transcript: str,
        patient: Patient,
        previous_extraction: Optional[ExtractionResult] = None
    ) -> ExtractionResult:
        """Extract structured data using Groq Llama API."""
        try:
            user_prompt = self._build_user_prompt(transcript, patient, previous_extraction)

            logger.debug(f"Sending extraction request for {len(transcript)} chars")

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=self.temperature,
                response_format={"type": "json_object"}
            )

            content = response.choices[0].message.content

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
