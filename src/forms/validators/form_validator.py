"""
Form validation for medical prescriptions and documents.
"""

import logging
from typing import Dict, Any, List, Tuple
from datetime import datetime, timedelta
import re

from ...config.settings import Config


class FormValidator:
    """Validates medical forms and prescriptions for completeness and accuracy."""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
    
    def validate_prescription_data(self, prescription_data: Dict[str, Any]) -> Tuple[bool, List[str], List[str]]:
        """
        Validate prescription data for completeness and accuracy.
        
        Args:
            prescription_data: Prescription data to validate
            
        Returns:
            Tuple of (is_valid, errors, warnings)
        """
        errors = []
        warnings = []
        
        # Required fields validation
        required_fields = self.config.forms.get('required_fields', [
            'patient_name', 'patient_id', 'doctor_name', 'doctor_license', 'medications'
        ])
        
        for field in required_fields:
            if not prescription_data.get(field):
                errors.append(f"Missing required field: {field}")
        
        # Validate patient information
        if prescription_data.get('patient_name'):
            if not self._is_valid_name(prescription_data['patient_name']):
                errors.append("Invalid patient name format")
        
        # Validate doctor information
        if prescription_data.get('doctor_license'):
            if not self._is_valid_license_format(prescription_data['doctor_license']):
                warnings.append("Doctor license format may be invalid")
        
        # Validate medications
        medications = prescription_data.get('medications', [])
        if medications:
            med_errors, med_warnings = self._validate_medications(medications)
            errors.extend(med_errors)
            warnings.extend(med_warnings)
        else:
            errors.append("No medications specified in prescription")
        
        # Validate dates
        prescription_date = prescription_data.get('prescription_date')
        if prescription_date:
            date_errors = self._validate_prescription_date(prescription_date)
            errors.extend(date_errors)
        
        is_valid = len(errors) == 0
        
        return is_valid, errors, warnings
    
    def _validate_medications(self, medications: List[Dict[str, Any]]) -> Tuple[List[str], List[str]]:
        """Validate medication list."""
        errors = []
        warnings = []
        
        for i, medication in enumerate(medications, 1):
            med_prefix = f"Medication {i}"
            
            # Check required medication fields
            if not medication.get('name'):
                errors.append(f"{med_prefix}: Missing medication name")
            else:
                # Validate medication name format
                if not self._is_valid_medication_name(medication['name']):
                    warnings.append(f"{med_prefix}: Medication name format may be unusual")
            
            # Validate dosage
            dosage = medication.get('dosage', '')
            if dosage and dosage != "As directed":
                if not self._is_valid_dosage_format(dosage):
                    warnings.append(f"{med_prefix}: Dosage format may be incorrect")
            
            # Validate frequency
            frequency = medication.get('frequency', '')
            if frequency and frequency != "As directed":
                if not self._is_valid_frequency_format(frequency):
                    warnings.append(f"{med_prefix}: Frequency format may be incorrect")
            
            # Check for dangerous combinations (simplified)
            if self._has_potential_interaction_warning(medication['name']):
                warnings.append(f"{med_prefix}: Potential drug interaction - verify with pharmacist")
        
        return errors, warnings
    
    def _is_valid_name(self, name: str) -> bool:
        """Validate patient/doctor name format."""
        if not name or len(name.strip()) < 2:
            return False
        
        # Check for reasonable name format (letters, spaces, hyphens, apostrophes)
        name_pattern = r"^[A-Za-z\s\-'\.]{2,50}$"
        return bool(re.match(name_pattern, name.strip()))
    
    def _is_valid_license_format(self, license_num: str) -> bool:
        """Validate doctor license number format."""
        if not license_num:
            return False
        
        # Simple format check - alphanumeric with possible hyphens/underscores
        license_pattern = r"^[A-Za-z0-9\-_]{5,20}$"
        return bool(re.match(license_pattern, license_num))
    
    def _is_valid_medication_name(self, name: str) -> bool:
        """Validate medication name format."""
        if not name or len(name.strip()) < 2:
            return False
        
        # Allow letters, numbers, spaces, hyphens, parentheses
        med_pattern = r"^[A-Za-z0-9\s\-\(\)]{2,50}$"
        return bool(re.match(med_pattern, name.strip()))
    
    def _is_valid_dosage_format(self, dosage: str) -> bool:
        """Validate dosage format."""
        if not dosage:
            return True  # Empty dosage is acceptable
        
        # Common dosage patterns
        dosage_patterns = [
            r'\d+\.?\d*\s*(mg|ml|g|mcg|units?)\b',
            r'\d+\s*(tablet|capsule|pill)s?\b',
            r'as\s+(directed|needed|prescribed)',
            r'one\s+(tablet|capsule|pill)',
            r'half\s+(tablet|capsule|pill)'
        ]
        
        dosage_lower = dosage.lower()
        return any(re.search(pattern, dosage_lower) for pattern in dosage_patterns)
    
    def _is_valid_frequency_format(self, frequency: str) -> bool:
        """Validate frequency format."""
        if not frequency:
            return True
        
        frequency_patterns = [
            r'once\s+(daily|a\s+day)',
            r'twice\s+(daily|a\s+day)',
            r'three\s+times\s+(daily|a\s+day)',
            r'\d+\s+times?\s+(daily|per\s+day)',
            r'every\s+\d+\s+hours?',
            r'as\s+(needed|directed)',
            r'before\s+(meals?|bed)',
            r'after\s+meals?',
            r'with\s+food'
        ]
        
        frequency_lower = frequency.lower()
        return any(re.search(pattern, frequency_lower) for pattern in frequency_patterns)
    
    def _validate_prescription_date(self, date_str: str) -> List[str]:
        """Validate prescription date."""
        errors = []
        
        try:
            prescription_date = datetime.strptime(date_str, '%Y-%m-%d')
            current_date = datetime.now()
            
            # Check if date is in the future (more than 1 day)
            if prescription_date > current_date + timedelta(days=1):
                errors.append("Prescription date cannot be in the future")
            
            # Check if date is too far in the past (more than 1 year)
            if prescription_date < current_date - timedelta(days=365):
                errors.append("Prescription date is unusually old (more than 1 year ago)")
            
        except ValueError:
            errors.append("Invalid prescription date format (expected YYYY-MM-DD)")
        
        return errors
    
    def _has_potential_interaction_warning(self, medication_name: str) -> bool:
        """Check for potential drug interactions (simplified)."""
        # This is a very simplified check - in production, use a comprehensive drug interaction database
        high_risk_medications = [
            'warfarin', 'coumadin', 'lithium', 'digoxin', 'theophylline'
        ]
        
        return any(risk_med in medication_name.lower() for risk_med in high_risk_medications)
    
    def validate_clinical_data(self, medical_data: Dict[str, Any]) -> Tuple[bool, List[str], List[str]]:
        """Validate clinical data for completeness."""
        errors = []
        warnings = []
        
        # Check for minimum clinical content
        if not any([
            medical_data.get('symptoms'),
            medical_data.get('diagnosis'),
            medical_data.get('clinical_summary')
        ]):
            errors.append("No clinical content found - symptoms, diagnosis, or summary required")
        
        # Validate confidence scores
        confidence_scores = medical_data.get('confidence_scores', {})
        overall_confidence = confidence_scores.get('overall', 0)
        
        if overall_confidence < 0.5:
            warnings.append(f"Low overall confidence score: {overall_confidence:.2f}")
        
        # Check for ICD codes if diagnosis present
        if medical_data.get('diagnosis') and not medical_data.get('icd_codes'):
            warnings.append("Diagnosis present but no ICD codes generated")
        
        # Validate transcript metadata
        transcript_metadata = medical_data.get('transcript_metadata', {})
        word_count = transcript_metadata.get('word_count', 0)
        
        if word_count < 50:
            warnings.append(f"Very short transcript: only {word_count} words")
        elif word_count > 5000:
            warnings.append(f"Very long transcript: {word_count} words")
        
        is_valid = len(errors) == 0
        
        return is_valid, errors, warnings