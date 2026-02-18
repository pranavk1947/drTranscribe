import os
import re
import yaml
from pathlib import Path
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv


class TranscriptionConfig(BaseModel):
    """Transcription service configuration."""
    provider: str
    model: str
    output_format: str = "wav"  # Format to send to provider: "wav" or "webm"


class ExtractionConfig(BaseModel):
    """Extraction service configuration."""
    provider: str
    model: str
    temperature: float = 0.3
    min_transcript_length: int = 50  # Minimum chars before triggering extraction


class OpenAIConfig(BaseModel):
    """OpenAI API configuration."""
    api_key: str


class AzureOpenAIConfig(BaseModel):
    """Azure OpenAI API configuration."""
    api_key: str
    endpoint: str
    api_version: str = "2024-08-01-preview"
    whisper_deployment: str = "whisper"
    gpt_deployment: str


class GroqConfig(BaseModel):
    """Groq API configuration."""
    api_key: str


class GeminiConfig(BaseModel):
    """Google Gemini API configuration."""
    api_key: str


class ClaudeConfig(BaseModel):
    """Claude (Anthropic) API configuration."""
    api_key: str


class ServerConfig(BaseModel):
    """Server configuration."""
    host: str = "0.0.0.0"
    port: int = 8000


class AudioSettings(BaseModel):
    """Audio capture configuration for real-time transcription"""
    chunk_duration_seconds: int = 5
    sample_rate: int = 16000
    channels: int = 1


class AudioStorageConfig(BaseModel):
    """Audio storage configuration."""
    enabled: bool = True
    temp_directory: str = "./data/temp/audio_chunks"
    output_directory: str = "./data/consultations"
    cleanup_temp_files: bool = True
    # Future: Add GCS config here
    # gcs_bucket: Optional[str] = None
    # gcs_credentials_path: Optional[str] = None


class Settings(BaseModel):
    """Application settings."""
    transcription: TranscriptionConfig
    extraction: ExtractionConfig
    openai: Optional[OpenAIConfig] = None
    azure_openai: Optional[AzureOpenAIConfig] = None
    claude: Optional[ClaudeConfig] = None
    groq: Optional[GroqConfig] = None
    gemini: Optional[GeminiConfig] = None
    server: ServerConfig
    audio: AudioSettings = AudioSettings()
    audio_storage: AudioStorageConfig = AudioStorageConfig()


def load_settings(config_path: str = None) -> Settings:
    """Load settings from YAML file with environment variable substitution."""
    # Load environment variables from .env file
    env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        print(f"✅ Loaded environment variables from {env_path}")

    if config_path is None:
        config_path = Path(__file__).parent.parent.parent / "config" / "settings.yaml"

    with open(config_path, 'r') as f:
        config_data = yaml.safe_load(f)

    # Substitute environment variables
    config_data = _substitute_env_vars(config_data)

    return Settings(**config_data)


def _substitute_env_vars(data: Any) -> Any:
    """Recursively substitute environment variables in config data."""
    if isinstance(data, dict):
        return {k: _substitute_env_vars(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_substitute_env_vars(item) for item in data]
    elif isinstance(data, str):
        # Replace ${VAR_NAME:default} or ${VAR_NAME} with environment variable value
        pattern = r'\$\{([^:}]+)(?::([^}]*))?\}'
        matches = re.findall(pattern, data)
        for var_name, default_value in matches:
            env_value = os.getenv(var_name, default_value)
            data = data.replace(f'${{{var_name}:{default_value}}}', env_value)
            data = data.replace(f'${{{var_name}}}', env_value)
        return data
    else:
        return data
