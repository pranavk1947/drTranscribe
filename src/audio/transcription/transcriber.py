"""
Audio transcription module supporting multiple speech-to-text providers.
"""

import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from abc import ABC, abstractmethod

import openai
import whisper
from azure.cognitiveservices.speech import SpeechConfig, AudioConfig, SpeechRecognizer
from google.cloud import speech

from ...config.settings import Config


class TranscriptionProvider(ABC):
    """Abstract base class for transcription providers."""
    
    @abstractmethod
    async def transcribe(self, audio_file: Path) -> Dict[str, Any]:
        """Transcribe audio file and return detailed results."""
        pass
    
    @abstractmethod
    async def health_check(self) -> str:
        """Check if the transcription service is available."""
        pass


class OpenAIWhisperProvider(TranscriptionProvider):
    """OpenAI Whisper transcription provider."""
    
    def __init__(self, config: Config):
        self.config = config
        self.client = openai.OpenAI(api_key=config.openai_api_key)
        self.logger = logging.getLogger(__name__)
    
    async def transcribe(self, audio_file: Path) -> Dict[str, Any]:
        """Transcribe using OpenAI Whisper API."""
        try:
            with open(audio_file, "rb") as audio:
                transcript = await asyncio.to_thread(
                    self.client.audio.transcriptions.create,
                    model=self.config.transcription.model,
                    file=audio,
                    response_format=self.config.transcription.response_format,
                    temperature=self.config.transcription.temperature,
                    timestamp_granularities=self.config.transcription.timestamp_granularities
                )
            
            return {
                'text': transcript.text,
                'segments': getattr(transcript, 'segments', []),
                'words': getattr(transcript, 'words', []),
                'language': getattr(transcript, 'language', 'en'),
                'duration': getattr(transcript, 'duration', None),
                'provider': 'openai_whisper'
            }
            
        except Exception as e:
            self.logger.error(f"OpenAI Whisper transcription failed: {str(e)}")
            raise
    
    async def health_check(self) -> str:
        """Check OpenAI API availability."""
        try:
            # Simple API call to check connectivity
            models = await asyncio.to_thread(self.client.models.list)
            return "healthy"
        except Exception:
            return "unhealthy"


class LocalWhisperProvider(TranscriptionProvider):
    """Local Whisper model transcription provider."""
    
    def __init__(self, config: Config):
        self.config = config
        self.model = None
        self.logger = logging.getLogger(__name__)
        self._load_model()
    
    def _load_model(self):
        """Load the local Whisper model."""
        try:
            model_name = self.config.transcription.model.replace("whisper-", "")
            self.model = whisper.load_model(model_name)
            self.logger.info(f"Loaded local Whisper model: {model_name}")
        except Exception as e:
            self.logger.error(f"Failed to load local Whisper model: {str(e)}")
            raise
    
    async def transcribe(self, audio_file: Path) -> Dict[str, Any]:
        """Transcribe using local Whisper model."""
        try:
            result = await asyncio.to_thread(
                self.model.transcribe,
                str(audio_file),
                temperature=self.config.transcription.temperature,
                language=self.config.transcription.language if self.config.transcription.language != "auto" else None,
                word_timestamps=True
            )
            
            return {
                'text': result['text'],
                'segments': result.get('segments', []),
                'words': self._extract_words_from_segments(result.get('segments', [])),
                'language': result.get('language', 'en'),
                'duration': max([seg.get('end', 0) for seg in result.get('segments', [])], default=0),
                'provider': 'local_whisper'
            }
            
        except Exception as e:
            self.logger.error(f"Local Whisper transcription failed: {str(e)}")
            raise
    
    def _extract_words_from_segments(self, segments: List[Dict]) -> List[Dict]:
        """Extract word-level timestamps from segments."""
        words = []
        for segment in segments:
            if 'words' in segment:
                words.extend(segment['words'])
        return words
    
    async def health_check(self) -> str:
        """Check if local model is loaded."""
        return "healthy" if self.model else "unhealthy"


class AzureSpeechProvider(TranscriptionProvider):
    """Azure Speech Services transcription provider."""
    
    def __init__(self, config: Config):
        self.config = config
        self.speech_config = SpeechConfig(
            subscription=config.azure_speech_key,
            region=config.azure_speech_region
        )
        self.speech_config.speech_recognition_language = config.transcription.language
        self.logger = logging.getLogger(__name__)
    
    async def transcribe(self, audio_file: Path) -> Dict[str, Any]:
        """Transcribe using Azure Speech Services."""
        try:
            audio_config = AudioConfig(filename=str(audio_file))
            speech_recognizer = SpeechRecognizer(
                speech_config=self.speech_config,
                audio_config=audio_config
            )
            
            result = await asyncio.to_thread(speech_recognizer.recognize_once)
            
            return {
                'text': result.text,
                'segments': [],  # Azure doesn't provide detailed segments in single recognition
                'words': [],
                'language': self.config.transcription.language,
                'duration': None,
                'provider': 'azure_speech',
                'confidence': getattr(result, 'confidence', None)
            }
            
        except Exception as e:
            self.logger.error(f"Azure Speech transcription failed: {str(e)}")
            raise
    
    async def health_check(self) -> str:
        """Check Azure Speech Services availability."""
        try:
            # Simple connection test
            speech_recognizer = SpeechRecognizer(speech_config=self.speech_config)
            return "healthy"
        except Exception:
            return "unhealthy"


class AudioTranscriber:
    """Main transcription orchestrator supporting multiple providers."""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.provider = self._get_provider()
    
    def _get_provider(self) -> TranscriptionProvider:
        """Get the configured transcription provider."""
        provider_name = self.config.transcription.provider.lower()
        
        if provider_name == "openai_whisper":
            return OpenAIWhisperProvider(self.config)
        elif provider_name == "local_whisper":
            return LocalWhisperProvider(self.config)
        elif provider_name == "azure_speech":
            return AzureSpeechProvider(self.config)
        else:
            raise ValueError(f"Unsupported transcription provider: {provider_name}")
    
    async def transcribe_audio(self, audio_file: Path) -> Dict[str, Any]:
        """
        Transcribe audio file with preprocessing and validation.
        
        Args:
            audio_file: Path to audio file
            
        Returns:
            Transcription results with metadata
        """
        try:
            # Validate audio file
            if not audio_file.exists():
                raise FileNotFoundError(f"Audio file not found: {audio_file}")
            
            # Check file format
            if audio_file.suffix.lower() not in self.config.audio.supported_formats:
                raise ValueError(f"Unsupported audio format: {audio_file.suffix}")
            
            # Check file size
            file_size_mb = audio_file.stat().st_size / (1024 * 1024)
            if file_size_mb > self.config.audio.max_file_size_mb:
                raise ValueError(f"Audio file too large: {file_size_mb:.1f}MB > {self.config.audio.max_file_size_mb}MB")
            
            self.logger.info(f"Starting transcription of {audio_file.name}")
            
            # Perform transcription
            result = await self.provider.transcribe(audio_file)
            
            # Add metadata
            result['file_path'] = str(audio_file)
            result['file_size_mb'] = file_size_mb
            result['word_count'] = len(result['text'].split())
            
            self.logger.info(f"Transcription completed: {result['word_count']} words")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Transcription failed for {audio_file}: {str(e)}")
            raise
    
    async def transcribe_batch(self, audio_files: List[Path]) -> List[Dict[str, Any]]:
        """Transcribe multiple audio files concurrently."""
        tasks = [self.transcribe_audio(file) for file in audio_files]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle exceptions in results
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self.logger.error(f"Batch transcription failed for {audio_files[i]}: {str(result)}")
                processed_results.append({
                    'error': str(result),
                    'file_path': str(audio_files[i]),
                    'status': 'failed'
                })
            else:
                result['status'] = 'completed'
                processed_results.append(result)
        
        return processed_results
    
    async def health_check(self) -> str:
        """Check transcription service health."""
        return await self.provider.health_check()