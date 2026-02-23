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

    async def save_chunk(
        self, session_id: str, chunk_bytes: bytes, chunk_index: int, source: str = "mic"
    ) -> Optional[Path]:
        """
        Save an audio chunk to temporary storage.

        Args:
            session_id: Session identifier
            chunk_bytes: WAV audio data
            chunk_index: Sequential chunk number (per-source)
            source: Audio source — "mic" (doctor) or "tab" (patient)

        Returns:
            Path to saved chunk file, or None if storage is disabled
        """
        if not self.config.enabled:
            logger.debug("Audio storage disabled, skipping chunk save")
            return None

        # Create session-specific temp directory
        session_temp_dir = self.temp_dir / session_id
        session_temp_dir.mkdir(parents=True, exist_ok=True)

        # Save chunk with source prefix + sequential naming for correct ordering
        chunk_path = session_temp_dir / f"{source}_chunk_{chunk_index:04d}.wav"

        # Write to disk asynchronously
        await asyncio.to_thread(chunk_path.write_bytes, chunk_bytes)

        logger.debug(f"Saved audio chunk: {chunk_path} ({len(chunk_bytes)} bytes)")
        return chunk_path

    async def combine_and_save(
        self,
        session_id: str,
        appointment_id: Optional[str],
        mic_chunk_paths: List[Path],
        tab_chunk_paths: List[Path],
        transcript: Optional[str] = None
    ) -> Optional[Path]:
        """
        Combine audio chunks per source track and save to final location.

        Mic (doctor) and tab (patient) chunks are saved as separate files
        to preserve correct chronological ordering within each track.
        Optionally saves a diarized transcript text file alongside audio.

        Args:
            session_id: Session identifier
            appointment_id: Appointment ID for file organization
            mic_chunk_paths: Mic (doctor) chunk file paths
            tab_chunk_paths: Tab (patient) chunk file paths
            transcript: Optional newline-formatted diarized transcript

        Returns:
            Path to output directory, or None on failure
        """
        if not self.config.enabled:
            logger.debug("Audio storage disabled, skipping combine")
            return None

        if not mic_chunk_paths and not tab_chunk_paths:
            logger.warning(f"No audio chunks to combine for session {session_id}")
            return None

        try:
            # Determine output directory
            if appointment_id:
                output_subdir = self.output_dir / f"appt_{appointment_id}"
            else:
                date_str = datetime.now().strftime("%Y-%m-%d")
                output_subdir = self.output_dir / date_str

            output_subdir.mkdir(parents=True, exist_ok=True)

            # Sort paths by filename to guarantee chronological order
            saved_paths = []

            if mic_chunk_paths:
                sorted_mic = sorted(mic_chunk_paths, key=lambda p: p.name)
                logger.info(f"Combining {len(sorted_mic)} mic (doctor) chunks for session {session_id}")
                combined_mic = await asyncio.to_thread(combine_wav_chunks, sorted_mic)
                mic_path = output_subdir / f"{session_id}_doctor.wav"
                await asyncio.to_thread(mic_path.write_bytes, combined_mic)
                saved_paths.append(mic_path)
                logger.info(f"Saved doctor audio: {mic_path} ({len(combined_mic)} bytes)")

            if tab_chunk_paths:
                sorted_tab = sorted(tab_chunk_paths, key=lambda p: p.name)
                logger.info(f"Combining {len(sorted_tab)} tab (patient) chunks for session {session_id}")
                combined_tab = await asyncio.to_thread(combine_wav_chunks, sorted_tab)
                tab_path = output_subdir / f"{session_id}_patient.wav"
                await asyncio.to_thread(tab_path.write_bytes, combined_tab)
                saved_paths.append(tab_path)
                logger.info(f"Saved patient audio: {tab_path} ({len(combined_tab)} bytes)")

            # Save diarized transcript alongside audio
            if transcript and transcript.strip():
                transcript_path = output_subdir / f"{session_id}_transcript.txt"
                await asyncio.to_thread(transcript_path.write_text, transcript, "utf-8")
                logger.info(f"Saved diarized transcript: {transcript_path}")

            logger.info(f"Audio saved to: {output_subdir} ({len(saved_paths)} track(s))")

            # Cleanup temp files if configured
            if self.config.cleanup_temp_files:
                await self._cleanup_temp_files(session_id)

            return output_subdir

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
