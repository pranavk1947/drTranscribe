"""
Medical NLP processor for extracting clinical information from transcripts.
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from transformers import AutoTokenizer, AutoModelForTokenClassification, pipeline
import spacy
from spacy import displacy

from ...config.settings import Config
from ..entity_extraction.extractor import MedicalEntityExtractor
from ..icd_coding.coder import ICDCoder


class MedicalNLPProcessor:
    """Main medical NLP processor orchestrating various medical text analysis tasks."""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Initialize components
        self.entity_extractor = MedicalEntityExtractor(config)
        self.icd_coder = ICDCoder(config)
        
        # Load clinical models
        self._load_models()
    
    def _load_models(self):
        """Load medical NLP models."""
        try:
            # Load clinical BERT for general medical text processing
            self.logger.info("Loading clinical NLP models...")
            
            # Medical entity recognition model
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.config.medical_nlp.entity_extraction_model
            )
            self.model = AutoModelForTokenClassification.from_pretrained(
                self.config.medical_nlp.entity_extraction_model
            )
            
            # Medical text classification pipeline
            self.medical_classifier = pipeline(
                "text-classification",
                model=self.config.medical_nlp.entity_extraction_model,
                tokenizer=self.tokenizer,
                max_length=self.config.medical_nlp.max_tokens
            )
            
            # Load spaCy model for additional medical processing
            try:
                self.nlp = spacy.load("en_core_sci_sm")  # SciSpaCy for medical texts
            except OSError:
                self.logger.warning("SciSpaCy model not found, using standard English model")
                self.nlp = spacy.load("en_core_web_sm")
            
            self.logger.info("Medical NLP models loaded successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to load medical NLP models: {str(e)}")
            raise
    
    async def process_transcript(self, transcript: Dict[str, Any], patient_id: str) -> Dict[str, Any]:
        """
        Process medical transcript and extract clinical information.
        
        Args:
            transcript: Transcription results from audio processor
            patient_id: Patient identifier for context
            
        Returns:
            Extracted medical information and entities
        """
        try:
            text = transcript.get('text', '')
            if not text.strip():
                return {'error': 'Empty transcript text'}
            
            self.logger.info(f"Processing medical transcript for patient {patient_id}")
            
            # Run all medical processing tasks concurrently
            tasks = [
                self._extract_medical_entities(text),
                self._extract_medications(text),
                self._extract_symptoms_diagnosis(text),
                self._extract_vital_signs(text),
                self._extract_procedures(text),
                self._generate_clinical_summary(text),
                self._extract_follow_up_instructions(text)
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            medical_entities = results[0] if not isinstance(results[0], Exception) else {}
            medications = results[1] if not isinstance(results[1], Exception) else []
            symptoms_diagnosis = results[2] if not isinstance(results[2], Exception) else {}
            vital_signs = results[3] if not isinstance(results[3], Exception) else {}
            procedures = results[4] if not isinstance(results[4], Exception) else []
            clinical_summary = results[5] if not isinstance(results[5], Exception) else ""
            follow_up = results[6] if not isinstance(results[6], Exception) else {}
            
            # Generate ICD codes
            icd_codes = await self.icd_coder.generate_icd_codes(
                symptoms_diagnosis.get('diagnosis', []),
                symptoms_diagnosis.get('symptoms', []),
                procedures
            )
            
            # Compile medical data
            medical_data = {
                'patient_id': patient_id,
                'timestamp': datetime.now().isoformat(),
                'transcript_metadata': {
                    'word_count': transcript.get('word_count', 0),
                    'duration': transcript.get('duration'),
                    'language': transcript.get('language', 'en')
                },
                'entities': medical_entities,
                'medications': medications,
                'symptoms': symptoms_diagnosis.get('symptoms', []),
                'diagnosis': symptoms_diagnosis.get('diagnosis', []),
                'vital_signs': vital_signs,
                'procedures': procedures,
                'icd_codes': icd_codes,
                'clinical_summary': clinical_summary,
                'follow_up_instructions': follow_up,
                'confidence_scores': self._calculate_confidence_scores(results),
                'processing_metadata': {
                    'model_version': self.config.medical_nlp.entity_extraction_model,
                    'processed_at': datetime.now().isoformat()
                }
            }
            
            self.logger.info(f"Medical processing completed for patient {patient_id}")
            
            return medical_data
            
        except Exception as e:
            self.logger.error(f"Medical processing failed for patient {patient_id}: {str(e)}")
            raise
    
    async def _extract_medical_entities(self, text: str) -> Dict[str, List[Dict]]:
        """Extract general medical entities using NER models."""
        return await asyncio.to_thread(self.entity_extractor.extract_entities, text)
    
    async def _extract_medications(self, text: str) -> List[Dict[str, Any]]:
        """Extract medication information including dosage and frequency."""
        medications = []
        
        # Use spaCy for medication extraction
        doc = await asyncio.to_thread(self.nlp, text)
        
        # Look for medication patterns
        medication_patterns = [
            "mg", "ml", "tablets", "capsules", "twice daily", "once daily",
            "morning", "evening", "before meals", "after meals"
        ]
        
        sentences = [sent.text for sent in doc.sents]
        
        for sentence in sentences:
            sentence_lower = sentence.lower()
            if any(pattern in sentence_lower for pattern in medication_patterns):
                # This is a simplified approach - in production, use specialized medication NER
                medication_info = {
                    'text': sentence.strip(),
                    'extracted_at': datetime.now().isoformat(),
                    'confidence': 0.8  # Placeholder confidence
                }
                medications.append(medication_info)
        
        return medications
    
    async def _extract_symptoms_diagnosis(self, text: str) -> Dict[str, List[str]]:
        """Extract symptoms and diagnoses from text."""
        doc = await asyncio.to_thread(self.nlp, text)
        
        symptoms = []
        diagnoses = []
        
        # Look for symptom and diagnosis patterns
        symptom_indicators = ["complains of", "reports", "experiencing", "symptoms include", "feels"]
        diagnosis_indicators = ["diagnosed with", "diagnosis", "condition", "has been found to have"]
        
        for sent in doc.sents:
            sent_text = sent.text.lower()
            
            # Check for symptoms
            if any(indicator in sent_text for indicator in symptom_indicators):
                symptoms.append(sent.text.strip())
            
            # Check for diagnoses
            if any(indicator in sent_text for indicator in diagnosis_indicators):
                diagnoses.append(sent.text.strip())
        
        return {
            'symptoms': symptoms,
            'diagnosis': diagnoses
        }
    
    async def _extract_vital_signs(self, text: str) -> Dict[str, Any]:
        """Extract vital signs measurements."""
        import re
        
        vital_patterns = {
            'blood_pressure': r'(\d{2,3})/(\d{2,3})\s*mmHg|BP:?\s*(\d{2,3})/(\d{2,3})',
            'heart_rate': r'HR:?\s*(\d{2,3})\s*bpm|heart rate:?\s*(\d{2,3})',
            'temperature': r'temp:?\s*(\d{2,3}(?:\.\d)?)\s*[°]?[FfCc]|(\d{2,3}(?:\.\d)?)\s*degrees',
            'respiratory_rate': r'RR:?\s*(\d{1,2})|respiratory rate:?\s*(\d{1,2})',
            'oxygen_saturation': r'O2:?\s*(\d{2,3})%|oxygen sat:?\s*(\d{2,3})%'
        }
        
        vitals = {}
        
        for vital_type, pattern in vital_patterns.items():
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                groups = [g for g in match.groups() if g is not None]
                if groups:
                    vitals[vital_type] = {
                        'value': groups[0],
                        'raw_text': match.group(0),
                        'position': match.span()
                    }
        
        return vitals
    
    async def _extract_procedures(self, text: str) -> List[Dict[str, Any]]:
        """Extract medical procedures mentioned in the transcript."""
        procedures = []
        
        # Common procedure keywords
        procedure_keywords = [
            "x-ray", "ultrasound", "MRI", "CT scan", "blood test", "urine test",
            "biopsy", "surgery", "injection", "vaccination", "examination",
            "EKG", "ECG", "endoscopy", "colonoscopy"
        ]
        
        text_lower = text.lower()
        
        for keyword in procedure_keywords:
            if keyword in text_lower:
                # Find sentences containing the procedure
                doc = await asyncio.to_thread(self.nlp, text)
                for sent in doc.sents:
                    if keyword in sent.text.lower():
                        procedures.append({
                            'procedure_type': keyword,
                            'context': sent.text.strip(),
                            'confidence': 0.9
                        })
        
        return procedures
    
    async def _generate_clinical_summary(self, text: str) -> str:
        """Generate a concise clinical summary."""
        # This is a simplified approach - in production, use a summarization model
        doc = await asyncio.to_thread(self.nlp, text)
        
        # Extract key sentences (simplified approach)
        sentences = [sent.text for sent in doc.sents]
        
        # Filter for clinically relevant sentences
        relevant_sentences = []
        clinical_keywords = [
            "diagnosis", "treatment", "medication", "symptoms", "condition",
            "prescribed", "recommended", "follow-up", "test results"
        ]
        
        for sentence in sentences:
            if any(keyword in sentence.lower() for keyword in clinical_keywords):
                relevant_sentences.append(sentence.strip())
        
        # Return first few relevant sentences as summary
        return " ".join(relevant_sentences[:3])
    
    async def _extract_follow_up_instructions(self, text: str) -> Dict[str, Any]:
        """Extract follow-up instructions and recommendations."""
        follow_up_keywords = [
            "follow up", "return in", "come back", "schedule", "appointment",
            "call if", "contact", "emergency", "seek medical attention"
        ]
        
        doc = await asyncio.to_thread(self.nlp, text)
        instructions = []
        
        for sent in doc.sents:
            if any(keyword in sent.text.lower() for keyword in follow_up_keywords):
                instructions.append(sent.text.strip())
        
        return {
            'instructions': instructions,
            'urgency': 'routine'  # This could be determined by keyword analysis
        }
    
    def _calculate_confidence_scores(self, results: List[Any]) -> Dict[str, float]:
        """Calculate overall confidence scores for extracted information."""
        # This is a simplified confidence calculation
        total_successful = sum(1 for result in results if not isinstance(result, Exception))
        overall_confidence = total_successful / len(results)
        
        return {
            'overall': overall_confidence,
            'entity_extraction': 0.85,  # These would be calculated based on model outputs
            'medication_extraction': 0.80,
            'diagnosis_extraction': 0.75,
            'procedure_extraction': 0.90
        }
    
    async def health_check(self) -> str:
        """Check if medical NLP models are loaded and functioning."""
        try:
            # Simple test processing
            test_text = "Patient reports headache and was prescribed ibuprofen."
            await asyncio.to_thread(self.nlp, test_text)
            return "healthy"
        except Exception:
            return "unhealthy"