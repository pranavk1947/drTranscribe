"""
DrTranscribe - AI Medical Transcription and Processing System

A comprehensive system for processing patient-doctor conversations,
extracting medical information, and automating prescription forms.
"""

__version__ = "1.0.0"
__author__ = "Loop Health"

from .main import DrTranscribeApp
from .config.settings import Config

__all__ = ["DrTranscribeApp", "Config"]