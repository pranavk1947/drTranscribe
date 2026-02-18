import asyncio
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
from .services.audio_storage import AudioStorageService
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
        session_manager: SessionManager,
        audio_storage_service: AudioStorageService
    ):
        self.settings = settings
        self.transcription_service = transcription_service
        self.extraction_service = extraction_service
        self.session_manager = session_manager
        self.audio_storage = audio_storage_service
    
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
                        # Extract any remaining transcript before ending session
                        session = self.session_manager.get_session(current_session_id)
                        if session:
                            full_transcript = session.get_full_transcript()
                            if full_transcript.strip():  # If there's ANY transcript left
                                logger.info(f"Final extraction on stop: {len(full_transcript)} chars")
                                try:
                                    await self._handle_extraction(
                                        session,
                                        full_transcript,
                                        websocket=None,  # Don't send update - client is stopping
                                        ignore_length_check=True  # Extract regardless of length
                                    )
                                except Exception as e:
                                    logger.error(f"Final extraction failed: {e}", exc_info=True)

                            # Combine and save audio in background
                            if session.audio_chunk_paths:
                                asyncio.create_task(
                                    self._save_session_audio(session)
                                )

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
                # Extract any remaining transcript before ending session
                session = self.session_manager.get_session(current_session_id)
                if session:
                    full_transcript = session.get_full_transcript()
                    if full_transcript.strip():  # If there's ANY transcript left
                        logger.info(f"Final extraction on disconnect: {len(full_transcript)} chars")
                        try:
                            await self._handle_extraction(
                                session,
                                full_transcript,
                                websocket=None,  # No websocket since connection is closed
                                ignore_length_check=True  # Extract regardless of length
                            )
                        except Exception as e:
                            logger.error(f"Final extraction failed: {e}", exc_info=True)

                    # Combine and save audio in background
                    if session.audio_chunk_paths:
                        asyncio.create_task(
                            self._save_session_audio(session)
                        )

                self.session_manager.end_session(current_session_id)

        except Exception as e:
            logger.error(f"WebSocket error: {str(e)}", exc_info=True)
            await self._send_error(websocket, f"Internal error: {str(e)}")
            if current_session_id:
                # Extract any remaining transcript before ending session
                session = self.session_manager.get_session(current_session_id)
                if session:
                    full_transcript = session.get_full_transcript()
                    if full_transcript.strip():  # If there's ANY transcript left
                        logger.info(f"Final extraction on error: {len(full_transcript)} chars")
                        try:
                            await self._handle_extraction(
                                session,
                                full_transcript,
                                websocket=None,  # No websocket since we're in error state
                                ignore_length_check=True  # Extract regardless of length
                            )
                        except Exception as ex:
                            logger.error(f"Final extraction failed: {ex}", exc_info=True)

                    # Combine and save audio in background
                    if session.audio_chunk_paths:
                        asyncio.create_task(
                            self._save_session_audio(session)
                        )

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

    async def _handle_extraction(
        self,
        session: ConsultationSession,
        full_transcript: str,
        websocket: Optional[WebSocket] = None,
        ignore_length_check: bool = False
    ):
        """Handle extraction of structured data from transcript.

        Args:
            session: The consultation session
            full_transcript: The full transcript text to extract from
            websocket: Optional websocket to send updates (if None, extraction is logged only)
            ignore_length_check: If True, skip minimum length validation (used for final extraction)
        """
        # Check minimum length unless explicitly ignored
        if not ignore_length_check:
            if len(full_transcript.strip()) < self.settings.extraction.min_transcript_length:
                logger.debug(
                    f"Transcript too short ({len(full_transcript)} chars), "
                    f"minimum required: {self.settings.extraction.min_transcript_length}, "
                    f"skipping extraction"
                )
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

        # Send update to frontend if websocket is provided
        if websocket:
            update_msg = ExtractionUpdateMessage(extraction=session.extraction)
            await websocket.send_text(update_msg.model_dump_json())
            logger.info(f"Sent extraction update for session {session.session_id}")

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

            # Save audio chunk to temp disk
            chunk_path = await self.audio_storage.save_chunk(
                session_id=session_id,
                chunk_bytes=audio_bytes,
                chunk_index=session.audio_chunk_count
            )
            if chunk_path:
                session.add_audio_chunk_path(chunk_path)
                session.audio_chunk_count += 1

            # Transcribe audio
            transcript = await self.transcription_service.transcribe(audio_bytes)
            if not transcript or not transcript.strip():
                logger.debug("Empty transcript, skipping extraction")
                return

            session.add_transcript_chunk(transcript)
            logger.info(f"Transcribed: {transcript[:100]}...")

            # Get full transcript for extraction
            full_transcript = session.get_full_transcript()

            # Handle extraction with length check
            await self._handle_extraction(session, full_transcript, websocket)

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

    async def _save_session_audio(self, session: ConsultationSession):
        """
        Background task to combine and save session audio.

        Runs asynchronously after stop_session response is sent.
        Doesn't block the WebSocket response.
        """
        try:
            logger.info(f"Background audio save started for session {session.session_id}")

            chunk_paths = session.get_audio_chunk_paths()
            saved_path = await self.audio_storage.combine_and_save(
                session_id=session.session_id,
                appointment_id=session.appointment_id,
                chunk_paths=chunk_paths
            )

            if saved_path:
                session.audio_saved_path = str(saved_path)
                logger.info(f"✅ Session audio saved: {saved_path}")
            else:
                logger.warning(f"Audio save failed for session {session.session_id}")

        except Exception as e:
            logger.error(
                f"Background audio save failed for session {session.session_id}: {e}",
                exc_info=True
            )
