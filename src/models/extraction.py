from pydantic import BaseModel, Field


class ExtractionResult(BaseModel):
    """Structured clinical data extraction result."""
    
    chief_complaint: str = Field(
        default="",
        description="Patient's symptoms with duration and severity, semicolon-separated. Only what the patient is physically or mentally experiencing."
    )
    diagnosis: str = Field(
        default="",
        description="Doctor's clinical assessment: identified condition, causes, triggers, risk factors, allergies, family history, and relevant lifestyle factors. Semicolon-separated."
    )
    medicine: str = Field(
        default="",
        description="Specific medications prescribed by the doctor with dosage and frequency. Semicolon-separated."
    )
    advice: str = Field(
        default="",
        description="Lifestyle recommendations and non-medication instructions from the doctor. Semicolon-separated."
    )
    next_steps: str = Field(
        default="",
        description="Concrete actions the patient must take after the consultation: lab tests, follow-ups, specialist referrals. Semicolon-separated."
    )
    
    def merge(self, other: 'ExtractionResult') -> 'ExtractionResult':
        """Merge with another extraction result (append new information)."""
        return ExtractionResult(
            chief_complaint=self._merge_field(self.chief_complaint, other.chief_complaint),
            diagnosis=self._merge_field(self.diagnosis, other.diagnosis),
            medicine=self._merge_field(self.medicine, other.medicine),
            advice=self._merge_field(self.advice, other.advice),
            next_steps=self._merge_field(self.next_steps, other.next_steps)
        )
    
    @staticmethod
    def _merge_field(existing: str, new: str) -> str:
        """Merge two field values with intelligent deduplication."""
        if not existing:
            return new
        if not new:
            return existing

        # Exact match
        if existing == new:
            return existing

        # Substring check (bidirectional)
        if new in existing:
            return existing  # New is subset of existing
        if existing in new:
            return new  # Existing is subset of new (new is more complete)

        # Split into lines and check for semantic overlap
        existing_lines = [line.strip() for line in existing.split('\n') if line.strip()]
        new_lines = [line.strip() for line in new.split('\n') if line.strip()]

        # Check if new lines are already in existing
        unique_new_lines = []
        for new_line in new_lines:
            is_duplicate = False
            for existing_line in existing_lines:
                # Check both directions for substring overlap
                if new_line in existing_line or existing_line in new_line:
                    is_duplicate = True
                    break
            if not is_duplicate:
                unique_new_lines.append(new_line)

        # Merge: keep existing + add only unique new lines
        if not unique_new_lines:
            return existing

        return existing + '\n' + '\n'.join(unique_new_lines)
