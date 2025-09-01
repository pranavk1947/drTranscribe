"""
Vector database module for DrTranscribe.

Handles patient history storage, embeddings, and semantic search.
"""

from .patient_history.history_manager import PatientHistoryManager
from .embeddings.embedding_generator import EmbeddingGenerator
from .search.semantic_search import SemanticSearchEngine

__all__ = ["PatientHistoryManager", "EmbeddingGenerator", "SemanticSearchEngine"]