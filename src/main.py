"""
Main application entry point for DrTranscribe system.
"""

import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, Optional

from .config.settings import Config
from .audio.transcription.transcriber import AudioTranscriber
from .medical.nlp.medical_processor import MedicalNLPProcessor
from .vector_db.patient_history.history_manager import PatientHistoryManager
from .forms.prescription.generator import PrescriptionGenerator
from .security.audit.audit_logger import AuditLogger


class DrTranscribeApp:
    """Main application orchestrating the medical transcription workflow."""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config = Config(config_path)
        self.transcriber = AudioTranscriber(self.config)
        self.nlp_processor = MedicalNLPProcessor(self.config)
        self.history_manager = PatientHistoryManager(self.config)
        self.prescription_generator = PrescriptionGenerator(self.config)
        self.audit_logger = AuditLogger(self.config)
        
        # Setup logging
        logging.basicConfig(
            level=getattr(logging, self.config.log_level),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(self.config.log_file),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    async def process_consultation(
        self, 
        audio_file: Path, 
        patient_id: str,
        doctor_id: str,
        session_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Process a complete consultation from audio to prescription.
        
        Args:
            audio_file: Path to the audio file
            patient_id: Unique patient identifier
            doctor_id: Unique doctor identifier
            session_metadata: Additional session information
            
        Returns:
            Complete consultation results including transcript, medical entities,
            and generated forms
        """
        try:
            # Log consultation start
            await self.audit_logger.log_consultation_start(
                patient_id, doctor_id, session_metadata
            )
            
            # Step 1: Transcribe audio
            self.logger.info(f"Starting transcription for patient {patient_id}")
            transcript = await self.transcriber.transcribe_audio(audio_file)
            
            # Step 2: Extract medical entities and information
            self.logger.info("Processing medical entities from transcript")
            medical_data = await self.nlp_processor.process_transcript(
                transcript, patient_id
            )
            
            # Step 3: Retrieve patient history for context
            self.logger.info(f"Retrieving patient history for {patient_id}")
            patient_context = await self.history_manager.get_patient_context(
                patient_id, medical_data
            )
            
            # Step 4: Update patient history with new information
            await self.history_manager.update_patient_history(
                patient_id, medical_data, transcript
            )
            
            # Step 5: Generate prescription if needed
            prescription = None
            if medical_data.get('medications') or medical_data.get('prescriptions'):
                self.logger.info("Generating prescription form")
                prescription = await self.prescription_generator.generate_prescription(
                    patient_id, doctor_id, medical_data, patient_context
                )
            
            # Compile results
            results = {
                'session_id': session_metadata.get('session_id'),
                'patient_id': patient_id,
                'doctor_id': doctor_id,
                'transcript': transcript,
                'medical_data': medical_data,
                'patient_context': patient_context,
                'prescription': prescription,
                'timestamp': session_metadata.get('timestamp'),
                'status': 'completed'
            }
            
            # Log successful completion
            await self.audit_logger.log_consultation_complete(
                patient_id, doctor_id, results
            )
            
            return results
            
        except Exception as e:
            self.logger.error(f"Error processing consultation: {str(e)}")
            await self.audit_logger.log_error(
                patient_id, doctor_id, str(e), session_metadata
            )
            raise
    
    async def health_check(self) -> Dict[str, str]:
        """Perform system health check."""
        return {
            'status': 'healthy',
            'transcriber': await self.transcriber.health_check(),
            'nlp_processor': await self.nlp_processor.health_check(),
            'vector_db': await self.history_manager.health_check(),
            'prescription_generator': await self.prescription_generator.health_check()
        }


async def main():
    """Main entry point for CLI usage."""
    import argparse
    
    parser = argparse.ArgumentParser(description='DrTranscribe Medical Transcription System')
    parser.add_argument('--audio', type=str, required=True, help='Path to audio file')
    parser.add_argument('--patient-id', type=str, required=True, help='Patient ID')
    parser.add_argument('--doctor-id', type=str, required=True, help='Doctor ID')
    parser.add_argument('--config', type=str, help='Path to config file')
    parser.add_argument('--session-id', type=str, help='Session ID')
    
    args = parser.parse_args()
    
    app = DrTranscribeApp(args.config)
    
    session_metadata = {
        'session_id': args.session_id or f"session_{patient_id}_{int(time.time())}",
        'timestamp': datetime.now().isoformat()
    }
    
    results = await app.process_consultation(
        Path(args.audio), 
        args.patient_id, 
        args.doctor_id, 
        session_metadata
    )
    
    print(f"Consultation processed successfully: {results['session_id']}")


if __name__ == "__main__":
    import time
    from datetime import datetime
    asyncio.run(main())