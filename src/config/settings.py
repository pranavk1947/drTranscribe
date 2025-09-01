"""
Configuration management for DrTranscribe system.
"""

import os
from pathlib import Path
from typing import Dict, Any, Optional
import yaml
from dataclasses import dataclass, field


@dataclass
class AudioConfig:
    """Audio processing configuration."""
    sample_rate: int = 16000
    chunk_size: int = 1024
    supported_formats: list = field(default_factory=lambda: ['.wav', '.mp3', '.m4a', '.flac'])
    noise_reduction: bool = True
    voice_activity_detection: bool = True
    max_file_size_mb: int = 100


@dataclass
class TranscriptionConfig:
    """Speech-to-text configuration."""
    provider: str = "openai_whisper"  # openai_whisper, azure_speech, google_speech
    model: str = "whisper-1"
    language: str = "en"
    temperature: float = 0.0
    response_format: str = "verbose_json"
    timestamp_granularities: list = field(default_factory=lambda: ["word", "segment"])


@dataclass
class MedicalNLPConfig:
    """Medical NLP processing configuration."""
    model_provider: str = "huggingface"  # huggingface, openai, azure
    entity_extraction_model: str = "clinical-bert-base-uncased"
    icd_coding_model: str = "microsoft/BiomedNLP-PubMedBERT-base-uncased-abstract-fulltext"
    medication_model: str = "allenai/scibert_scivocab_uncased"
    confidence_threshold: float = 0.85
    max_tokens: int = 4096


@dataclass
class VectorDBConfig:
    """Vector database configuration."""
    provider: str = "chroma"  # chroma, pinecone, weaviate, qdrant
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    collection_name: str = "patient_history"
    dimension: int = 384
    similarity_metric: str = "cosine"
    max_results: int = 10
    persist_directory: str = "./data/vector_store"


@dataclass
class SecurityConfig:
    """Security and compliance configuration."""
    encryption_key_path: str = "./config/encryption.key"
    enable_audit_logging: bool = True
    audit_log_path: str = "./logs/audit.log"
    data_retention_days: int = 2555  # 7 years for medical records
    enable_phi_detection: bool = True
    anonymize_transcripts: bool = False


@dataclass
class DatabaseConfig:
    """Database configuration."""
    url: str = "postgresql://localhost:5432/drtranscribe"
    echo: bool = False
    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout: int = 30


class Config:
    """Main configuration class."""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or os.getenv("DR_TRANSCRIBE_CONFIG", "./config/config.yaml")
        
        # Default configurations
        self.audio = AudioConfig()
        self.transcription = TranscriptionConfig()
        self.medical_nlp = MedicalNLPConfig()
        self.vector_db = VectorDBConfig()
        self.security = SecurityConfig()
        self.database = DatabaseConfig()
        
        # Application settings
        self.app_name = "DrTranscribe"
        self.version = "1.0.0"
        self.environment = os.getenv("ENVIRONMENT", "development")
        self.debug = os.getenv("DEBUG", "false").lower() == "true"
        self.log_level = os.getenv("LOG_LEVEL", "INFO")
        self.log_file = "./logs/app.log"
        
        # API Keys and Secrets (from environment variables)
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.azure_speech_key = os.getenv("AZURE_SPEECH_KEY")
        self.azure_speech_region = os.getenv("AZURE_SPEECH_REGION")
        self.google_credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        self.pinecone_api_key = os.getenv("PINECONE_API_KEY")
        
        # Load configuration from file if it exists
        self._load_config()
    
    def _load_config(self):
        """Load configuration from YAML file."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    config_data = yaml.safe_load(f)
                
                if config_data:
                    self._update_from_dict(config_data)
            except Exception as e:
                print(f"Warning: Could not load config file {self.config_path}: {e}")
    
    def _update_from_dict(self, config_dict: Dict[str, Any]):
        """Update configuration from dictionary."""
        for section, values in config_dict.items():
            if hasattr(self, section) and isinstance(getattr(self, section), (AudioConfig, TranscriptionConfig, MedicalNLPConfig, VectorDBConfig, SecurityConfig, DatabaseConfig)):
                config_obj = getattr(self, section)
                for key, value in values.items():
                    if hasattr(config_obj, key):
                        setattr(config_obj, key, value)
            else:
                # Set application-level configuration
                if hasattr(self, section):
                    setattr(self, section, values)
    
    def save_config(self, path: Optional[str] = None):
        """Save current configuration to YAML file."""
        save_path = path or self.config_path
        
        config_dict = {
            'audio': self.audio.__dict__,
            'transcription': self.transcription.__dict__,
            'medical_nlp': self.medical_nlp.__dict__,
            'vector_db': self.vector_db.__dict__,
            'security': self.security.__dict__,
            'database': self.database.__dict__,
            'app_name': self.app_name,
            'version': self.version,
            'environment': self.environment,
            'debug': self.debug,
            'log_level': self.log_level,
            'log_file': self.log_file
        }
        
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        
        with open(save_path, 'w') as f:
            yaml.dump(config_dict, f, default_flow_style=False, indent=2)
    
    def validate(self) -> bool:
        """Validate configuration settings."""
        errors = []
        
        # Check required API keys based on providers
        if self.transcription.provider == "openai_whisper" and not self.openai_api_key:
            errors.append("OpenAI API key is required for Whisper transcription")
        
        if self.transcription.provider == "azure_speech" and (not self.azure_speech_key or not self.azure_speech_region):
            errors.append("Azure Speech key and region are required for Azure Speech Service")
        
        if self.vector_db.provider == "pinecone" and not self.pinecone_api_key:
            errors.append("Pinecone API key is required for Pinecone vector database")
        
        # Check file paths
        if not os.path.exists(os.path.dirname(self.log_file)):
            os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        
        if errors:
            print("Configuration validation errors:")
            for error in errors:
                print(f"  - {error}")
            return False
        
        return True
    
    def get_model_cache_dir(self) -> Path:
        """Get the directory for caching ML models."""
        cache_dir = Path("./data/models")
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir