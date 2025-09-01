"""
Semantic search engine for patient medical history using vector database.
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
import numpy as np

from ...config.settings import Config
from ..embeddings.embedding_generator import EmbeddingGenerator


class SemanticSearchEngine:
    """Semantic search engine for medical records using vector similarity."""
    
    def __init__(self, config: Config, vector_client, collection):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.vector_client = vector_client
        self.collection = collection
        self.embedding_generator = EmbeddingGenerator(config)
    
    async def semantic_search(
        self, 
        query: str, 
        patient_id: Optional[str] = None,
        max_results: int = None,
        similarity_threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        Perform semantic search on medical records.
        
        Args:
            query: Search query text
            patient_id: Optional patient ID to filter results
            max_results: Maximum number of results to return
            similarity_threshold: Minimum similarity score threshold
            
        Returns:
            List of matching medical records with similarity scores
        """
        try:
            if not query.strip():
                return []
            
            max_results = max_results or self.config.vector_db.max_results
            
            # Generate query embedding
            query_embedding = await self.embedding_generator.generate_embedding(query)
            
            # Prepare search filters
            where_filter = {}
            if patient_id:
                where_filter['patient_id'] = patient_id
            
            # Perform vector search
            search_results = await asyncio.to_thread(
                self.collection.query,
                query_embeddings=[query_embedding.tolist()],
                n_results=max_results,
                where=where_filter if where_filter else None
            )
            
            # Process and format results
            formatted_results = []
            if search_results['ids'] and search_results['ids'][0]:
                for i, result_id in enumerate(search_results['ids'][0]):
                    similarity_score = 1 - search_results['distances'][0][i]  # Convert distance to similarity
                    
                    if similarity_score >= similarity_threshold:
                        result = {
                            'id': result_id,
                            'content': search_results['documents'][0][i],
                            'metadata': search_results['metadatas'][0][i],
                            'similarity_score': similarity_score,
                            'query': query
                        }
                        formatted_results.append(result)
            
            # Sort by similarity score
            formatted_results.sort(key=lambda x: x['similarity_score'], reverse=True)
            
            self.logger.info(f"Semantic search returned {len(formatted_results)} results for query: '{query[:50]}...'")
            
            return formatted_results
            
        except Exception as e:
            self.logger.error(f"Semantic search failed: {str(e)}")
            return []
    
    async def find_similar_consultations(
        self, 
        medical_data: Dict[str, Any], 
        patient_id: str,
        max_results: int = 5
    ) -> List[Dict[str, Any]]:
        """Find consultations similar to the current medical data."""
        try:
            # Create search query from medical data
            query_parts = []
            
            if medical_data.get('symptoms'):
                query_parts.extend(medical_data['symptoms'])
            
            if medical_data.get('diagnosis'):
                query_parts.extend(medical_data['diagnosis'])
            
            if medical_data.get('clinical_summary'):
                query_parts.append(medical_data['clinical_summary'])
            
            if not query_parts:
                return []
            
            query = " ".join(query_parts[:5])  # Limit query length
            
            # Perform search excluding current consultation
            similar_consultations = await self.semantic_search(
                query, 
                patient_id=patient_id, 
                max_results=max_results + 1  # Get extra in case current consultation is included
            )
            
            # Filter out current consultation if it exists
            current_timestamp = medical_data.get('timestamp')
            if current_timestamp:
                similar_consultations = [
                    consultation for consultation in similar_consultations
                    if consultation.get('metadata', {}).get('timestamp') != current_timestamp
                ]
            
            return similar_consultations[:max_results]
            
        except Exception as e:
            self.logger.error(f"Failed to find similar consultations: {str(e)}")
            return []
    
    async def search_by_medical_entity(
        self, 
        entity_type: str, 
        entity_value: str,
        patient_id: Optional[str] = None,
        max_results: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search for records containing specific medical entities.
        
        Args:
            entity_type: Type of entity (e.g., 'medication', 'diagnosis', 'symptom')
            entity_value: Value of the entity to search for
            patient_id: Optional patient ID to filter results
            max_results: Maximum number of results
            
        Returns:
            List of matching records
        """
        try:
            # Create entity-specific search query
            if entity_type == 'medication':
                query = f"medication {entity_value} prescribed treatment"
            elif entity_type == 'diagnosis':
                query = f"diagnosis {entity_value} condition disease"
            elif entity_type == 'symptom':
                query = f"symptom {entity_value} complaint"
            else:
                query = f"{entity_type} {entity_value}"
            
            return await self.semantic_search(
                query, 
                patient_id=patient_id, 
                max_results=max_results
            )
            
        except Exception as e:
            self.logger.error(f"Medical entity search failed: {str(e)}")
            return []
    
    async def search_by_date_range(
        self, 
        start_date: str, 
        end_date: str,
        patient_id: Optional[str] = None,
        query: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search for records within a specific date range."""
        try:
            # Prepare filters
            where_filter = {
                "timestamp": {"$gte": start_date, "$lte": end_date}
            }
            
            if patient_id:
                where_filter["patient_id"] = patient_id
            
            if query:
                # Semantic search with date filter
                query_embedding = await self.embedding_generator.generate_embedding(query)
                
                search_results = await asyncio.to_thread(
                    self.collection.query,
                    query_embeddings=[query_embedding.tolist()],
                    n_results=50,  # Get more results for date filtering
                    where=where_filter
                )
            else:
                # Just retrieve records in date range
                search_results = await asyncio.to_thread(
                    self.collection.query,
                    query_texts=[""],  # Empty query to get all matching metadata
                    n_results=100,
                    where=where_filter
                )
            
            # Format results
            formatted_results = []
            if search_results['ids'] and search_results['ids'][0]:
                for i, result_id in enumerate(search_results['ids'][0]):
                    result = {
                        'id': result_id,
                        'content': search_results['documents'][0][i],
                        'metadata': search_results['metadatas'][0][i],
                        'similarity_score': 1 - search_results['distances'][0][i] if query else 1.0
                    }
                    formatted_results.append(result)
            
            return formatted_results
            
        except Exception as e:
            self.logger.error(f"Date range search failed: {str(e)}")
            return []
    
    async def get_patient_summary_statistics(self, patient_id: str) -> Dict[str, Any]:
        """Get summary statistics for a patient's medical records."""
        try:
            # Get all patient records
            patient_records = await asyncio.to_thread(
                self.collection.query,
                query_texts=[""],
                n_results=1000,  # Large number to get all records
                where={"patient_id": patient_id}
            )
            
            if not patient_records['ids'] or not patient_records['ids'][0]:
                return {'total_records': 0}
            
            total_records = len(patient_records['ids'][0])
            
            # Analyze metadata
            metadatas = patient_records['metadatas'][0]
            
            # Count records with different attributes
            has_diagnosis = sum(1 for m in metadatas if m.get('has_diagnosis', False))
            has_medications = sum(1 for m in metadatas if m.get('has_medications', False))
            has_procedures = sum(1 for m in metadatas if m.get('has_procedures', False))
            
            # Calculate average confidence
            confidence_scores = [m.get('confidence_score', 0) for m in metadatas if m.get('confidence_score')]
            avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0
            
            # Get date range
            timestamps = [m.get('timestamp') for m in metadatas if m.get('timestamp')]
            timestamps.sort()
            
            statistics = {
                'patient_id': patient_id,
                'total_records': total_records,
                'records_with_diagnosis': has_diagnosis,
                'records_with_medications': has_medications,
                'records_with_procedures': has_procedures,
                'average_confidence_score': avg_confidence,
                'first_record_date': timestamps[0] if timestamps else None,
                'latest_record_date': timestamps[-1] if timestamps else None,
                'date_range_days': (
                    (pd.to_datetime(timestamps[-1]) - pd.to_datetime(timestamps[0])).days
                    if len(timestamps) > 1 else 0
                )
            }
            
            return statistics
            
        except Exception as e:
            self.logger.error(f"Failed to get patient statistics: {str(e)}")
            return {'total_records': 0, 'error': str(e)}