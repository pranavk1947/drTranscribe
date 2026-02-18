"""Service for storing consultation audio files."""
import asyncio
import logging
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from ..config.settings import Settings
from ..utils.wav_utils import combine_wav_chunks

logger = logging.getLogger(__name__)


class AudioStorageService:
    """Handles saving and managing consultation audio files."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.config = settings.audio_storage

        # Create directories if they don't exist
        self.temp_dir = Path(self.config.temp_directory)
        self.output_dir = Path(self.config.output_directory)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Audio storage initialized: temp={self.temp_dir}, output={self.output_dir}")

    async def save_chunk(self, session_id: str, chunk_bytes: bytes, chunk_index: int) -> Optional[Path]:
        """
        Save an audio chunk to temporary storage.

        Args:
            session_id: Session identifier
            chunk_bytes: WAV audio data
            chunk_index: Sequential chunk number

        Returns:
            Path to saved chunk file, or None if storage is disabled
        """
        if not self.config.enabled:
            logger.debug("Audio storage disabled, skipping chunk save")
            return None

        # Create session-specific temp directory
        session_temp_dir = self.temp_dir / session_id
        session_temp_dir.mkdir(parents=True, exist_ok=True)

        # Save chunk with sequential naming
        chunk_path = session_temp_dir / f"chunk_{chunk_index:04d}.wav"

        # Write to disk asynchronously
        await asyncio.to_thread(chunk_path.write_bytes, chunk_bytes)

        logger.debug(f"Saved audio chunk: {chunk_path} ({len(chunk_bytes)} bytes)")
        return chunk_path

    async def combine_and_save(
        self,
        session_id: str,
        appointment_id: Optional[str],
        chunk_paths: List[Path]
    ) -> Optional[Path]:
        """
        Combine audio chunks and save to final location.

        This runs in background - doesn't block the response.

        Args:
            session_id: Session identifier
            appointment_id: Appointment ID for file organization
            chunk_paths: List of temp chunk file paths

        Returns:
            Path to final saved audio file, or None on failure
        """
        if not self.config.enabled:
            logger.debug("Audio storage disabled, skipping combine")
            return None

        if not chunk_paths:
            logger.warning(f"No audio chunks to combine for session {session_id}")
            return None

        try:
            logger.info(f"Combining {len(chunk_paths)} audio chunks for session {session_id}")

            # Combine chunks into single WAV
            combined_wav = await asyncio.to_thread(combine_wav_chunks, chunk_paths)

            # Determine output path
            if appointment_id:
                # Organize by appointment ID: consultations/appt_12345/audio.wav
                output_subdir = self.output_dir / f"appt_{appointment_id}"
            else:
                # Fallback: organize by date and session
                date_str = datetime.now().strftime("%Y-%m-%d")
                output_subdir = self.output_dir / date_str

            output_subdir.mkdir(parents=True, exist_ok=True)
            output_path = output_subdir / f"{session_id}_audio.wav"

            # Save combined audio
            await asyncio.to_thread(output_path.write_bytes, combined_wav)

            logger.info(
                f"✅ Audio saved: {output_path} "
                f"({len(combined_wav)} bytes, {len(chunk_paths)} chunks)"
            )

            # Cleanup temp files if configured
            if self.config.cleanup_temp_files:
                await self._cleanup_temp_files(session_id)

            return output_path

        except Exception as e:
            logger.error(f"Failed to combine and save audio for session {session_id}: {e}", exc_info=True)
            return None

    async def _cleanup_temp_files(self, session_id: str):
        """Remove temporary chunk files for a session."""
        try:
            session_temp_dir = self.temp_dir / session_id
            if session_temp_dir.exists():
                await asyncio.to_thread(self._remove_directory, session_temp_dir)
                logger.debug(f"Cleaned up temp files for session {session_id}")
        except Exception as e:
            logger.warning(f"Failed to cleanup temp files for session {session_id}: {e}")

    @staticmethod
    def _remove_directory(path: Path):
        """Synchronously remove directory and contents."""
        import shutil
        shutil.rmtree(path)
