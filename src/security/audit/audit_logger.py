"""
HIPAA-compliant audit logging for medical data access and processing.
"""

import asyncio
import logging
import json
from typing import Dict, Any, Optional
from datetime import datetime
import hashlib

from ...config.settings import Config


class AuditLogger:
    """HIPAA-compliant audit logger for medical data access and operations."""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger("audit_logger")
        
        # Setup audit log file handler
        if config.security.enable_audit_logging:
            audit_handler = logging.FileHandler(config.security.audit_log_path)
            audit_formatter = logging.Formatter(
                '%(asctime)s - AUDIT - %(levelname)s - %(message)s'
            )
            audit_handler.setFormatter(audit_formatter)
            self.logger.addHandler(audit_handler)
            self.logger.setLevel(logging.INFO)
    
    async def log_consultation_start(
        self, 
        patient_id: str, 
        doctor_id: str, 
        session_metadata: Dict[str, Any]
    ):
        """Log the start of a medical consultation processing."""
        audit_entry = {
            'event_type': 'consultation_start',
            'timestamp': datetime.now().isoformat(),
            'patient_id_hash': self._hash_identifier(patient_id),
            'doctor_id_hash': self._hash_identifier(doctor_id),
            'session_id': session_metadata.get('session_id'),
            'user_agent': session_metadata.get('user_agent'),
            'ip_address': session_metadata.get('ip_address'),
            'action': 'Medical consultation processing initiated'
        }
        
        self.logger.info(json.dumps(audit_entry))
    
    async def log_consultation_complete(
        self, 
        patient_id: str, 
        doctor_id: str, 
        results: Dict[str, Any]
    ):
        """Log successful completion of consultation processing."""
        audit_entry = {
            'event_type': 'consultation_complete',
            'timestamp': datetime.now().isoformat(),
            'patient_id_hash': self._hash_identifier(patient_id),
            'doctor_id_hash': self._hash_identifier(doctor_id),
            'session_id': results.get('session_id'),
            'processing_duration': results.get('processing_duration'),
            'components_processed': {
                'transcription': 'transcript' in results,
                'medical_nlp': 'medical_data' in results,
                'prescription': 'prescription' in results,
                'patient_history': 'patient_context' in results
            },
            'action': 'Medical consultation processing completed successfully'
        }
        
        self.logger.info(json.dumps(audit_entry))
    
    async def log_data_access(
        self, 
        user_id: str, 
        patient_id: str, 
        data_type: str, 
        action: str,
        additional_info: Optional[Dict[str, Any]] = None
    ):
        """Log patient data access events."""
        audit_entry = {
            'event_type': 'data_access',
            'timestamp': datetime.now().isoformat(),
            'user_id_hash': self._hash_identifier(user_id),
            'patient_id_hash': self._hash_identifier(patient_id),
            'data_type': data_type,  # e.g., 'medical_record', 'prescription', 'audio_file'
            'action': action,  # e.g., 'read', 'write', 'delete', 'export'
            'additional_info': additional_info or {}
        }
        
        self.logger.info(json.dumps(audit_entry))
    
    async def log_prescription_generated(
        self, 
        patient_id: str, 
        doctor_id: str, 
        prescription_id: str,
        medications: list
    ):
        """Log prescription generation events."""
        audit_entry = {
            'event_type': 'prescription_generated',
            'timestamp': datetime.now().isoformat(),
            'patient_id_hash': self._hash_identifier(patient_id),
            'doctor_id_hash': self._hash_identifier(doctor_id),
            'prescription_id': prescription_id,
            'medication_count': len(medications),
            'medications_hash': self._hash_identifier(str(medications)),
            'action': 'Prescription generated from AI-processed consultation'
        }
        
        self.logger.info(json.dumps(audit_entry))
    
    async def log_error(
        self, 
        patient_id: str, 
        doctor_id: str, 
        error_message: str,
        session_metadata: Dict[str, Any]
    ):
        """Log processing errors with patient context."""
        audit_entry = {
            'event_type': 'processing_error',
            'timestamp': datetime.now().isoformat(),
            'patient_id_hash': self._hash_identifier(patient_id),
            'doctor_id_hash': self._hash_identifier(doctor_id),
            'session_id': session_metadata.get('session_id'),
            'error_type': type(error_message).__name__ if hasattr(error_message, '__name__') else 'Unknown',
            'error_message_hash': self._hash_identifier(error_message),
            'action': 'Processing failed with error'
        }
        
        self.logger.error(json.dumps(audit_entry))
    
    async def log_authentication_event(
        self, 
        user_id: str, 
        event_type: str, 
        success: bool,
        additional_info: Optional[Dict[str, Any]] = None
    ):
        """Log user authentication events."""
        audit_entry = {
            'event_type': f'auth_{event_type}',
            'timestamp': datetime.now().isoformat(),
            'user_id_hash': self._hash_identifier(user_id),
            'success': success,
            'action': f"User {event_type} {'successful' if success else 'failed'}",
            'additional_info': additional_info or {}
        }
        
        self.logger.info(json.dumps(audit_entry))
    
    async def log_system_event(
        self, 
        event_type: str, 
        description: str,
        additional_info: Optional[Dict[str, Any]] = None
    ):
        """Log system-level events."""
        audit_entry = {
            'event_type': f'system_{event_type}',
            'timestamp': datetime.now().isoformat(),
            'description': description,
            'additional_info': additional_info or {},
            'action': f"System event: {description}"
        }
        
        self.logger.info(json.dumps(audit_entry))
    
    def _hash_identifier(self, identifier: str) -> str:
        """Hash patient/user identifiers for audit logging privacy."""
        if not identifier:
            return "unknown"
        
        # Use SHA-256 for one-way hashing of identifiers
        return hashlib.sha256(identifier.encode()).hexdigest()[:16]  # Truncate for readability