"""
ICD-10-CM coding from medical diagnoses and conditions.
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
import json
from pathlib import Path

from ...config.settings import Config


class ICDCoder:
    """Generate ICD-10-CM codes from medical diagnoses and symptoms."""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Load ICD code mappings
        self._load_icd_mappings()
    
    def _load_icd_mappings(self):
        """Load ICD-10-CM code mappings."""
        # This would typically load from a comprehensive ICD database
        # For this example, we'll use a simplified mapping
        self.icd_mappings = {
            # Common symptoms
            'headache': {'code': 'R51', 'description': 'Headache'},
            'fever': {'code': 'R50.9', 'description': 'Fever, unspecified'},
            'cough': {'code': 'R05', 'description': 'Cough'},
            'chest pain': {'code': 'R07.89', 'description': 'Other chest pain'},
            'shortness of breath': {'code': 'R06.02', 'description': 'Shortness of breath'},
            'nausea': {'code': 'R11.10', 'description': 'Vomiting, unspecified'},
            'dizziness': {'code': 'R42', 'description': 'Dizziness and giddiness'},
            'fatigue': {'code': 'R53.1', 'description': 'Weakness'},
            
            # Common conditions
            'hypertension': {'code': 'I10', 'description': 'Essential hypertension'},
            'diabetes': {'code': 'E11.9', 'description': 'Type 2 diabetes mellitus without complications'},
            'asthma': {'code': 'J45.9', 'description': 'Asthma, unspecified'},
            'pneumonia': {'code': 'J18.9', 'description': 'Pneumonia, unspecified organism'},
            'bronchitis': {'code': 'J20.9', 'description': 'Acute bronchitis, unspecified'},
            'anxiety': {'code': 'F41.9', 'description': 'Anxiety disorder, unspecified'},
            'depression': {'code': 'F32.9', 'description': 'Major depressive disorder, single episode, unspecified'},
            'arthritis': {'code': 'M19.90', 'description': 'Unspecified osteoarthritis, unspecified site'},
            'migraine': {'code': 'G43.909', 'description': 'Migraine, unspecified, not intractable, without status migrainosus'},
            'gastritis': {'code': 'K29.70', 'description': 'Gastritis, unspecified, without bleeding'},
            
            # Procedures (ICD-10-PCS would be more appropriate, but including some common ones)
            'blood test': {'code': '30230N1', 'description': 'Transfusion of Nonautologous Red Blood Cells into Peripheral Vein, Percutaneous Approach'},
            'x-ray': {'code': 'BN00ZZZ', 'description': 'Plain Radiography of Skull and Facial Bones'},
            'ct scan': {'code': 'B020YZZ', 'description': 'CT Scan of Brain'},
            'mri': {'code': 'B030YZZ', 'description': 'MRI of Brain'},
        }
    
    async def generate_icd_codes(
        self, 
        diagnoses: List[str], 
        symptoms: List[str], 
        procedures: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Generate ICD codes from diagnoses, symptoms, and procedures.
        
        Args:
            diagnoses: List of diagnosed conditions
            symptoms: List of reported symptoms
            procedures: List of performed procedures
            
        Returns:
            List of ICD codes with descriptions and confidence scores
        """
        try:
            icd_codes = []
            
            # Process diagnoses (highest priority)
            for diagnosis in diagnoses:
                codes = await self._find_icd_codes_for_text(diagnosis, 'diagnosis')
                icd_codes.extend(codes)
            
            # Process symptoms
            for symptom in symptoms:
                codes = await self._find_icd_codes_for_text(symptom, 'symptom')
                icd_codes.extend(codes)
            
            # Process procedures
            for procedure in procedures:
                procedure_text = procedure.get('procedure_type', '') or procedure.get('context', '')
                if procedure_text:
                    codes = await self._find_icd_codes_for_text(procedure_text, 'procedure')
                    icd_codes.extend(codes)
            
            # Remove duplicates and sort by confidence
            icd_codes = self._deduplicate_codes(icd_codes)
            icd_codes.sort(key=lambda x: x['confidence'], reverse=True)
            
            self.logger.info(f"Generated {len(icd_codes)} ICD codes")
            
            return icd_codes
            
        except Exception as e:
            self.logger.error(f"ICD code generation failed: {str(e)}")
            return []
    
    async def _find_icd_codes_for_text(self, text: str, text_type: str) -> List[Dict[str, Any]]:
        """Find ICD codes for a given medical text."""
        codes = []
        text_lower = text.lower().strip()
        
        # Direct mapping lookup
        for condition, icd_info in self.icd_mappings.items():
            if condition in text_lower:
                code_info = {
                    'icd_code': icd_info['code'],
                    'description': icd_info['description'],
                    'matched_text': condition,
                    'original_text': text,
                    'confidence': self._calculate_confidence(condition, text_lower, text_type),
                    'category': self._determine_icd_category(icd_info['code']),
                    'text_type': text_type
                }
                codes.append(code_info)
        
        # Fuzzy matching for partial matches
        if not codes:
            fuzzy_matches = await self._fuzzy_match_icd_codes(text_lower, text_type)
            codes.extend(fuzzy_matches)
        
        return codes
    
    async def _fuzzy_match_icd_codes(self, text: str, text_type: str) -> List[Dict[str, Any]]:
        """Perform fuzzy matching for ICD codes."""
        matches = []
        
        # Simple keyword-based fuzzy matching
        keywords = text.split()
        
        for condition, icd_info in self.icd_mappings.items():
            condition_words = condition.split()
            
            # Calculate word overlap
            common_words = set(keywords).intersection(set(condition_words))
            if common_words and len(common_words) >= min(2, len(condition_words)):
                match_score = len(common_words) / max(len(keywords), len(condition_words))
                
                if match_score > 0.3:  # Minimum similarity threshold
                    code_info = {
                        'icd_code': icd_info['code'],
                        'description': icd_info['description'],
                        'matched_text': condition,
                        'original_text': text,
                        'confidence': match_score * 0.7,  # Reduce confidence for fuzzy matches
                        'category': self._determine_icd_category(icd_info['code']),
                        'text_type': text_type,
                        'match_type': 'fuzzy'
                    }
                    matches.append(code_info)
        
        return matches
    
    def _calculate_confidence(self, matched_condition: str, text: str, text_type: str) -> float:
        """Calculate confidence score for ICD code match."""
        base_confidence = 0.9
        
        # Exact match gets full confidence
        if matched_condition == text:
            return base_confidence
        
        # Partial match reduces confidence
        if matched_condition in text:
            match_ratio = len(matched_condition) / len(text)
            confidence = base_confidence * match_ratio
        else:
            confidence = base_confidence * 0.7
        
        # Adjust based on text type
        if text_type == 'diagnosis':
            confidence *= 1.0  # No adjustment for diagnoses
        elif text_type == 'symptom':
            confidence *= 0.8  # Slightly less confident for symptoms
        elif text_type == 'procedure':
            confidence *= 0.9  # High confidence for procedures
        
        return min(confidence, 1.0)
    
    def _determine_icd_category(self, icd_code: str) -> str:
        """Determine ICD category from code."""
        if not icd_code:
            return 'unknown'
        
        # ICD-10-CM category mapping based on first character
        category_map = {
            'A': 'Infectious and parasitic diseases',
            'B': 'Infectious and parasitic diseases',
            'C': 'Neoplasms',
            'D': 'Diseases of blood and immune system',
            'E': 'Endocrine, nutritional and metabolic diseases',
            'F': 'Mental and behavioral disorders',
            'G': 'Diseases of the nervous system',
            'H': 'Diseases of the eye and ear',
            'I': 'Diseases of the circulatory system',
            'J': 'Diseases of the respiratory system',
            'K': 'Diseases of the digestive system',
            'L': 'Diseases of the skin',
            'M': 'Diseases of the musculoskeletal system',
            'N': 'Diseases of the genitourinary system',
            'O': 'Pregnancy, childbirth and the puerperium',
            'P': 'Perinatal conditions',
            'Q': 'Congenital malformations',
            'R': 'Symptoms, signs and abnormal findings',
            'S': 'Injury, poisoning',
            'T': 'Injury, poisoning',
            'V': 'External causes of morbidity',
            'W': 'External causes of morbidity',
            'X': 'External causes of morbidity',
            'Y': 'External causes of morbidity',
            'Z': 'Factors influencing health status'
        }
        
        first_char = icd_code[0].upper() if icd_code else ''
        return category_map.get(first_char, 'unknown')
    
    def _deduplicate_codes(self, codes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate ICD codes."""
        seen_codes = set()
        deduplicated = []
        
        for code in codes:
            code_key = code['icd_code']
            if code_key not in seen_codes:
                seen_codes.add(code_key)
                deduplicated.append(code)
            else:
                # If we've seen this code before, keep the one with higher confidence
                existing_index = next(
                    i for i, c in enumerate(deduplicated) 
                    if c['icd_code'] == code_key
                )
                if code['confidence'] > deduplicated[existing_index]['confidence']:
                    deduplicated[existing_index] = code
        
        return deduplicated
    
    async def validate_icd_codes(self, codes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Validate generated ICD codes."""
        validation_result = {
            'valid_codes': [],
            'invalid_codes': [],
            'warnings': []
        }
        
        for code in codes:
            icd_code = code['icd_code']
            
            # Basic validation - check if code matches ICD-10 format
            if self._is_valid_icd10_format(icd_code):
                validation_result['valid_codes'].append(code)
            else:
                validation_result['invalid_codes'].append(code)
                validation_result['warnings'].append(
                    f"Invalid ICD-10 format: {icd_code}"
                )
            
            # Check confidence threshold
            if code['confidence'] < self.config.medical_nlp.confidence_threshold:
                validation_result['warnings'].append(
                    f"Low confidence for code {icd_code}: {code['confidence']:.2f}"
                )
        
        return validation_result
    
    def _is_valid_icd10_format(self, code: str) -> bool:
        """Check if code follows ICD-10 format."""
        if not code:
            return False
        
        # Basic ICD-10-CM format check (letter followed by 2-7 alphanumeric characters)
        import re
        pattern = r'^[A-Z]\d{2}(\.[A-Z0-9]{1,4})?$'
        return bool(re.match(pattern, code))