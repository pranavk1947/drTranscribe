"""
Medical processing module for DrTranscribe.

Handles medical NLP, entity extraction, ICD coding, and clinical note processing.
"""

from .nlp.medical_processor import MedicalNLPProcessor
from .entity_extraction.extractor import MedicalEntityExtractor
from .icd_coding.coder import ICDCoder

__all__ = ["MedicalNLPProcessor", "MedicalEntityExtractor", "ICDCoder"]