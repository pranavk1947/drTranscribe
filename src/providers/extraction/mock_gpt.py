import logging
import asyncio
from typing import Optional
from ..base import ExtractionProvider
from ...models.extraction import ExtractionResult
from ...models.patient import Patient

logger = logging.getLogger(__name__)


class MockGPTProvider(ExtractionProvider):
    """Mock extraction provider for testing without GPT API."""
    
    def __init__(self, **kwargs):
        self.call_count = 0
        logger.info("⚠️  Using MOCK extraction (simulated GPT)")
        logger.info("   Real extraction requires Azure/OpenAI GPT")
    
    async def extract(
        self,
        transcript: str,
        patient: Patient,
        previous_extraction: Optional[ExtractionResult] = None
    ) -> ExtractionResult:
        """Simulate extraction with realistic medical data."""
        await asyncio.sleep(0.3)
        
        self.call_count += 1
        
        # Build extraction based on transcript content
        extraction = ExtractionResult()
        
        transcript_lower = transcript.lower()
        
        # Chief Complaint
        if any(word in transcript_lower for word in ['headache', 'head', 'pain']):
            extraction.chief_complaint = "Severe headaches for the past week, pain level 8/10"
        elif any(word in transcript_lower for word in ['cough', 'cold', 'fever']):
            extraction.chief_complaint = "Cough and cold with mild fever for 3 days"
        elif any(word in transcript_lower for word in ['stomach', 'abdomen', 'pain']):
            extraction.chief_complaint = "Abdominal pain and discomfort"
        else:
            extraction.chief_complaint = "Patient reports discomfort and seeks medical attention"
        
        # Diagnosis
        if self.call_count >= 2:
            if 'headache' in transcript_lower or 'head' in transcript_lower:
                extraction.diagnosis = "Tension headaches, possibly stress-related"
            elif 'cough' in transcript_lower or 'cold' in transcript_lower:
                extraction.diagnosis = "Upper respiratory tract infection"
            else:
                extraction.diagnosis = "Under evaluation, awaiting further tests"
        
        # Medicine
        if self.call_count >= 3:
            if 'headache' in transcript_lower:
                extraction.medicine = "Ibuprofen 400mg, twice daily with food"
            elif 'cough' in transcript_lower or 'cold' in transcript_lower:
                extraction.medicine = "Paracetamol 500mg, three times daily"
            else:
                extraction.medicine = "Prescription provided"
        
        # Advice
        if self.call_count >= 4:
            extraction.advice = "Reduce screen time, take regular breaks every hour, practice relaxation techniques, maintain proper hydration"
        
        # Next Steps
        if self.call_count >= 5:
            extraction.next_steps = "Blood test to check for vitamin deficiencies, follow-up appointment in two weeks"
        
        logger.info(f"📝 Mock extraction #{self.call_count}: Generated based on transcript")
        
        return extraction
