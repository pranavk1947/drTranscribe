import json
import logging
import base64
import struct
import uuid
from typing import Optional
from fastapi import WebSocket, WebSocketDisconnect
from .services.transcription_service import TranscriptionService
from .services.extraction_service import ExtractionService
from .services.session_manager import SessionManager
from .models.consultation import ConsultationSession
from .models.patient import Patient
from .models.websocket_messages import (
    StartSessionMessage,
    AudioChunkMessage,
    StopSessionMessage,
    ExtractionUpdateMessage,
    ErrorMessage
)
from .config.settings import Settings

logger = logging.getLogger(__name__)


class WebSocketHandler:
    """WebSocket connection handler for real-time transcription."""
    
    def __init__(
        self,
        settings: Settings,
        transcription_service: TranscriptionService,
        extraction_service: ExtractionService,
        session_manager: SessionManager
    ):
        self.settings = settings
        self.transcription_service = transcription_service
        self.extraction_service = extraction_service
        self.session_manager = session_manager
    
    async def handle_connection(self, websocket: WebSocket):
        """Handle WebSocket connection lifecycle."""
        await websocket.accept()
        current_session_id: Optional[str] = None
        
        try:
            while True:
                data = await websocket.receive_text()
                message = json.loads(data)
                message_type = message.get("type")
                
                logger.debug(f"Received message type: {message_type}")
                
                if message_type == "start_session":
                    current_session_id = await self._handle_start_session(
                        websocket, message
                    )
                
                elif message_type == "audio_chunk":
                    if not current_session_id:
                        await self._send_error(
                            websocket,
                            "No active session. Start a session first."
                        )
                        continue
                    
                    await self._handle_audio_chunk(
                        websocket, current_session_id, message
                    )
                
                elif message_type == "stop_session":
                    if current_session_id:
                        self.session_manager.end_session(current_session_id)
                        current_session_id = None
                    break
                
                else:
                    await self._send_error(
                        websocket,
                        f"Unknown message type: {message_type}"
                    )
        
        except WebSocketDisconnect:
            logger.info("WebSocket disconnected")
            if current_session_id:
                self.session_manager.end_session(current_session_id)
        
        except Exception as e:
            logger.error(f"WebSocket error: {str(e)}", exc_info=True)
            await self._send_error(websocket, f"Internal error: {str(e)}")
            if current_session_id:
                self.session_manager.end_session(current_session_id)
    
    async def _handle_start_session(
        self,
        websocket: WebSocket,
        message: dict
    ) -> str:
        """Handle start session message."""
        try:
            start_msg = StartSessionMessage(**message)
            session_id = str(uuid.uuid4())

            session = ConsultationSession(
                session_id=session_id,
                patient=start_msg.patient,
                appointment_id=start_msg.appointmentId
            )

            # Log appointment ID if provided
            if start_msg.appointmentId:
                logger.info(f"Session started for appointment: {start_msg.appointmentId}")

            self.session_manager.create_session(session)
            logger.info(f"Started session {session_id} for patient: {start_msg.patient.name}")

            return session_id
        
        except Exception as e:
            logger.error(f"Failed to start session: {str(e)}")
            await self._send_error(websocket, f"Failed to start session: {str(e)}")
            raise
    
    @staticmethod
    def _is_silent_wav(audio_bytes: bytes, rms_threshold: float = 200.0) -> bool:
        """
        Check if a WAV audio chunk is effectively silent.

        Parses the WAV header to find Int16 PCM data and computes RMS energy.
        Silent or near-silent audio causes Gemini to hallucinate entire
        conversations, so we must skip these chunks.

        Args:
            audio_bytes: Raw WAV file bytes (44-byte header + Int16 PCM)
            rms_threshold: RMS energy below this = silence (scale: 0-32768)

        Returns:
            True if audio is silent/near-silent
        """
        try:
            if len(audio_bytes) <= 44:
                return True

            # WAV PCM data starts at byte 44
            pcm_data = audio_bytes[44:]
            num_samples = len(pcm_data) // 2

            if num_samples == 0:
                return True

            # Parse Int16 samples and compute RMS
            samples = struct.unpack(f'<{num_samples}h', pcm_data[:num_samples * 2])
            sum_sq = sum(s * s for s in samples)
            rms = (sum_sq / num_samples) ** 0.5

            logger.debug(f"Audio RMS energy: {rms:.1f} (threshold: {rms_threshold})")
            return rms < rms_threshold
        except Exception as e:
            logger.warning(f"Silence detection failed, processing anyway: {e}")
            return False

    async def _handle_audio_chunk(
        self,
        websocket: WebSocket,
        session_id: str,
        message: dict
    ):
        """Handle audio chunk message and process pipeline."""
        try:
            audio_msg = AudioChunkMessage(**message)
            session = self.session_manager.get_session(session_id)

            if not session:
                await self._send_error(websocket, "Session not found")
                return

            # Decode Base64 audio data
            audio_bytes = base64.b64decode(audio_msg.audio_data)
            logger.debug(f"Received {len(audio_bytes)} bytes of audio")

            # Skip silent chunks to prevent Gemini hallucination
            if self._is_silent_wav(audio_bytes):
                logger.debug("Silent audio chunk, skipping transcription")
                return

            # Transcribe audio
            transcript = await self.transcription_service.transcribe(audio_bytes)
            if not transcript or not transcript.strip():
                logger.debug("Empty transcript, skipping extraction")
                return
            
            session.add_transcript_chunk(transcript)
            logger.info(f"Transcribed: {transcript[:100]}...")

            # Get full transcript for extraction
            full_transcript = session.get_full_transcript()

            # Only extract if we have substantial content
            # Skip extraction for very short transcripts (< 50 chars)
            if len(full_transcript.strip()) < 50:
                logger.debug(f"Transcript too short ({len(full_transcript)} chars), skipping extraction")
                return

            # Extract structured data
            extraction = await self.extraction_service.extract(
                transcript=full_transcript,
                patient=session.patient,
                previous_extraction=session.extraction
            )

            # Log what changed
            if session.extraction:
                changed_fields = []
                if extraction.chief_complaint != session.extraction.chief_complaint:
                    changed_fields.append(f"chief_complaint: '{session.extraction.chief_complaint}' -> '{extraction.chief_complaint}'")
                if extraction.diagnosis != session.extraction.diagnosis:
                    changed_fields.append(f"diagnosis: '{session.extraction.diagnosis}' -> '{extraction.diagnosis}'")
                if extraction.medicine != session.extraction.medicine:
                    changed_fields.append(f"medicine: '{session.extraction.medicine}' -> '{extraction.medicine}'")
                if extraction.advice != session.extraction.advice:
                    changed_fields.append(f"advice: '{session.extraction.advice}' -> '{extraction.advice}'")
                if extraction.next_steps != session.extraction.next_steps:
                    changed_fields.append(f"next_steps: '{session.extraction.next_steps}' -> '{extraction.next_steps}'")

                if changed_fields:
                    logger.info(f"Extraction changes: {'; '.join(changed_fields)}")
            else:
                logger.info(f"First extraction: {extraction.model_dump()}")

            # Merge with session extraction
            session.update_extraction(extraction)

            # Send update to frontend
            update_msg = ExtractionUpdateMessage(extraction=session.extraction)
            await websocket.send_text(update_msg.model_dump_json())

            logger.info(f"Sent extraction update for session {session_id}")
        
        except (WebSocketDisconnect, RuntimeError) as e:
            logger.warning(f"WebSocket closed during audio processing: {e}")
        except Exception as e:
            logger.error(f"Failed to process audio chunk: {str(e)}", exc_info=True)
            await self._send_error(websocket, f"Failed to process audio: {str(e)}")
    
    async def _send_error(self, websocket: WebSocket, message: str):
        """Send error message to client."""
        try:
            error_msg = ErrorMessage(message=message)
            await websocket.send_text(error_msg.model_dump_json())
        except Exception as e:
            logger.error(f"Failed to send error message: {str(e)}")
