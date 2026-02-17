import json
import logging
from typing import Optional
from anthropic import AsyncAnthropic
from ..base import ExtractionProvider, ExtractionError
from ...models.extraction import ExtractionResult
from ...models.patient import Patient

logger = logging.getLogger(__name__)


class ClaudeGPTProvider(ExtractionProvider):
    """Claude (Anthropic) extraction provider."""

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
- NEVER fill fields with what "would typically be prescribed"
- If the doctor has NOT mentioned a field yet, return an EMPTY STRING "" for that field
- Medical accuracy requires ZERO hallucination, ZERO prediction, ZERO suggestions
- When in doubt, leave the field EMPTY
- Empty is better than wrong or assumed

**CRITICAL: Format Requirements**
- Return valid JSON with exact keys: chief_complaint, diagnosis, medicine, advice, next_steps
- ALL field values MUST be single strings, NOT arrays or lists
- If multiple pieces of information exist for a field, combine them into ONE string separated by semicolons
- Example: {"medicine": "Ibuprofen 400mg twice daily; Vitamin B complex once daily"}
- Example EMPTY field: {"medicine": ""}

**CRITICAL: Merging Instructions (when previous extraction provided)**
You will receive:
1. Current transcript chunk (new audio)
2. Previous extraction (cumulative so far)

Your job:
- Read what doctor said in CURRENT transcript
- Look at PREVIOUS extraction
- For each field, ADD new info to existing info (if any)
- NEVER remove or replace existing valid information
- NEVER repeat the same information twice
- If current chunk adds nothing new to a field, keep the previous value unchanged
- If current chunk contradicts previous (e.g., doctor corrects diagnosis), REPLACE with new value
- Separate multiple items with semicolons

**Merging Examples:**

Example 1 - Adding new medicine:
Previous: {"medicine": "Paracetamol 500mg"}
Current chunk: "Also take vitamin C"
Result: {"medicine": "Paracetamol 500mg; Vitamin C"}

Example 2 - Field was empty, now has value:
Previous: {"diagnosis": ""}
Current chunk: "I think you have viral fever"
Result: {"diagnosis": "Viral fever"}

Example 3 - No new info in field:
Previous: {"chief_complaint": "Headache for 3 days"}
Current chunk: "Take rest"
Result: {"chief_complaint": "Headache for 3 days"}  // Unchanged

Example 4 - Correction/replacement:
Previous: {"diagnosis": "Possible migraine"}
Current chunk: "Actually, on second thought, this is tension headache"
Result: {"diagnosis": "Tension headache"}  // Replaced

Return ONLY the complete merged JSON object with all 5 fields."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-3-5-sonnet-20241022",
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
                system=self.SYSTEM_PROMPT,
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
