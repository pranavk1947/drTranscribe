"""
Embedding generation for medical text using sentence transformers.
"""

import asyncio
import logging
import numpy as np
from typing import Union, List
from sentence_transformers import SentenceTransformer

from ...config.settings import Config


class EmbeddingGenerator:
    """Generate embeddings for medical text using sentence transformers."""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self._load_model()
    
    def _load_model(self):
        """Load the sentence transformer model."""
        try:
            self.model = SentenceTransformer(self.config.vector_db.embedding_model)
            self.logger.info(f"Loaded embedding model: {self.config.vector_db.embedding_model}")
        except Exception as e:
            self.logger.error(f"Failed to load embedding model: {str(e)}")
            raise
    
    async def generate_embedding(self, text: Union[str, List[str]]) -> np.ndarray:
        """
        Generate embeddings for text.
        
        Args:
            text: Text string or list of text strings
            
        Returns:
            Numpy array of embeddings
        """
        try:
            # Generate embeddings using sentence transformer
            embeddings = await asyncio.to_thread(self.model.encode, text)
            
            # Ensure we return the correct shape
            if isinstance(text, str):
                return embeddings
            else:
                return embeddings
            
        except Exception as e:
            self.logger.error(f"Failed to generate embeddings: {str(e)}")
            raise
    
    async def generate_batch_embeddings(self, texts: List[str], batch_size: int = 32) -> np.ndarray:
        """Generate embeddings for a batch of texts."""
        try:
            all_embeddings = []
            
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                batch_embeddings = await self.generate_embedding(batch)
                all_embeddings.append(batch_embeddings)
            
            return np.vstack(all_embeddings)
            
        except Exception as e:
            self.logger.error(f"Failed to generate batch embeddings: {str(e)}")
            raise
    
    def get_embedding_dimension(self) -> int:
        """Get the dimension of the embedding model."""
        return self.model.get_sentence_embedding_dimension()