"""
Patient history management using vector database for semantic search and context retrieval.
"""

import asyncio
import logging
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from pathlib import Path

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

from ...config.settings import Config
from ..embeddings.embedding_generator import EmbeddingGenerator
from ..search.semantic_search import SemanticSearchEngine


class PatientHistoryManager:
    """Manages patient medical history using vector database for semantic search."""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Initialize vector database client
        self._initialize_vector_db()
        
        # Initialize embedding generator and search engine
        self.embedding_generator = EmbeddingGenerator(config)
        self.search_engine = SemanticSearchEngine(config, self.client, self.collection)
    
    def _initialize_vector_db(self):
        """Initialize the vector database client and collection."""
        try:
            if self.config.vector_db.provider == "chroma":
                # Initialize ChromaDB
                persist_dir = Path(self.config.vector_db.persist_directory)
                persist_dir.mkdir(parents=True, exist_ok=True)
                
                self.client = chromadb.PersistentClient(
                    path=str(persist_dir),
                    settings=Settings(
                        anonymized_telemetry=False,
                        allow_reset=True
                    )
                )
                
                # Get or create collection
                self.collection = self.client.get_or_create_collection(
                    name=self.config.vector_db.collection_name,
                    metadata={
                        "description": "Patient medical history and clinical notes",
                        "embedding_model": self.config.vector_db.embedding_model,
                        "dimension": self.config.vector_db.dimension
                    }
                )
                
                self.logger.info(f"ChromaDB initialized with collection: {self.config.vector_db.collection_name}")
            
            else:
                raise ValueError(f"Unsupported vector DB provider: {self.config.vector_db.provider}")
                
        except Exception as e:
            self.logger.error(f"Failed to initialize vector database: {str(e)}")
            raise
    
    async def store_patient_record(
        self, 
        patient_id: str, 
        medical_data: Dict[str, Any],
        transcript_text: str
    ) -> str:
        """
        Store a new patient medical record in the vector database.
        
        Args:
            patient_id: Unique patient identifier
            medical_data: Processed medical information
            transcript_text: Original transcript text
            
        Returns:
            Record ID for the stored document
        """
        try:
            # Create document ID
            timestamp = datetime.now().isoformat()
            record_id = f"{patient_id}_{timestamp}"
            
            # Prepare document content for embedding
            document_content = self._prepare_document_content(medical_data, transcript_text)
            
            # Generate embeddings
            embedding = await self.embedding_generator.generate_embedding(document_content)
            
            # Prepare metadata
            metadata = {
                'patient_id': patient_id,
                'timestamp': timestamp,
                'record_type': 'consultation',
                'has_diagnosis': len(medical_data.get('diagnosis', [])) > 0,
                'has_medications': len(medical_data.get('medications', [])) > 0,
                'has_procedures': len(medical_data.get('procedures', [])) > 0,
                'word_count': medical_data.get('transcript_metadata', {}).get('word_count', 0),
                'confidence_score': medical_data.get('confidence_scores', {}).get('overall', 0.0)
            }
            
            # Add ICD codes to metadata if present
            if medical_data.get('icd_codes'):
                metadata['icd_codes'] = json.dumps(medical_data['icd_codes'])
            
            # Store in vector database
            await asyncio.to_thread(
                self.collection.add,
                ids=[record_id],
                embeddings=[embedding.tolist()],
                documents=[document_content],
                metadatas=[metadata]
            )
            
            self.logger.info(f"Stored medical record for patient {patient_id}: {record_id}")
            
            return record_id
            
        except Exception as e:
            self.logger.error(f"Failed to store patient record for {patient_id}: {str(e)}")
            raise
    
    async def get_patient_context(
        self, 
        patient_id: str, 
        current_medical_data: Dict[str, Any],
        max_history_months: int = 12
    ) -> Dict[str, Any]:
        """
        Retrieve relevant patient context based on current medical data.
        
        Args:
            patient_id: Patient identifier
            current_medical_data: Current consultation medical data
            max_history_months: Maximum months of history to consider
            
        Returns:
            Patient context including relevant historical information
        """
        try:
            # Get recent patient history
            cutoff_date = datetime.now() - timedelta(days=max_history_months * 30)
            
            # Search for patient's historical records
            patient_history = await self._get_patient_history(patient_id, cutoff_date)
            
            # Find semantically similar past consultations
            if current_medical_data.get('symptoms') or current_medical_data.get('diagnosis'):
                query_text = self._create_search_query(current_medical_data)
                similar_consultations = await self.search_engine.semantic_search(
                    query_text, 
                    patient_id=patient_id,
                    max_results=5
                )
            else:
                similar_consultations = []
            
            # Extract medication history
            medication_history = self._extract_medication_history(patient_history)
            
            # Extract chronic conditions
            chronic_conditions = self._extract_chronic_conditions(patient_history)
            
            # Extract allergy information
            allergies = self._extract_allergies(patient_history)
            
            # Generate patient summary
            patient_summary = self._generate_patient_summary(
                patient_history, 
                medication_history, 
                chronic_conditions
            )
            
            context = {
                'patient_id': patient_id,
                'generated_at': datetime.now().isoformat(),
                'history_period_months': max_history_months,
                'total_consultations': len(patient_history),
                'patient_summary': patient_summary,
                'recent_consultations': patient_history[:3],  # Most recent 3
                'similar_consultations': similar_consultations,
                'medication_history': medication_history,
                'chronic_conditions': chronic_conditions,
                'known_allergies': allergies,
                'risk_factors': self._identify_risk_factors(patient_history)
            }
            
            self.logger.info(f"Retrieved context for patient {patient_id}: {len(patient_history)} records")
            
            return context
            
        except Exception as e:
            self.logger.error(f"Failed to get patient context for {patient_id}: {str(e)}")
            raise
    
    async def update_patient_history(
        self, 
        patient_id: str, 
        medical_data: Dict[str, Any], 
        transcript_text: str
    ) -> str:
        """Update patient history with new consultation data."""
        return await self.store_patient_record(patient_id, medical_data, transcript_text)
    
    async def search_patient_records(
        self, 
        query: str, 
        patient_id: Optional[str] = None,
        max_results: int = 10
    ) -> List[Dict[str, Any]]:
        """Search patient records using semantic search."""
        return await self.search_engine.semantic_search(
            query, patient_id=patient_id, max_results=max_results
        )
    
    def _prepare_document_content(self, medical_data: Dict[str, Any], transcript_text: str) -> str:
        """Prepare document content for embedding generation."""
        content_parts = []
        
        # Add clinical summary
        if medical_data.get('clinical_summary'):
            content_parts.append(f"Summary: {medical_data['clinical_summary']}")
        
        # Add symptoms
        if medical_data.get('symptoms'):
            symptoms_text = "; ".join(medical_data['symptoms'])
            content_parts.append(f"Symptoms: {symptoms_text}")
        
        # Add diagnosis
        if medical_data.get('diagnosis'):
            diagnosis_text = "; ".join(medical_data['diagnosis'])
            content_parts.append(f"Diagnosis: {diagnosis_text}")
        
        # Add medications
        if medical_data.get('medications'):
            medication_texts = []
            for med in medical_data['medications']:
                if isinstance(med, dict):
                    medication_texts.append(med.get('text', str(med)))
                else:
                    medication_texts.append(str(med))
            content_parts.append(f"Medications: {'; '.join(medication_texts)}")
        
        # Add procedures
        if medical_data.get('procedures'):
            procedure_texts = []
            for proc in medical_data['procedures']:
                if isinstance(proc, dict):
                    procedure_texts.append(proc.get('context', str(proc)))
                else:
                    procedure_texts.append(str(proc))
            content_parts.append(f"Procedures: {'; '.join(procedure_texts)}")
        
        # Add follow-up instructions
        if medical_data.get('follow_up_instructions', {}).get('instructions'):
            follow_up_text = "; ".join(medical_data['follow_up_instructions']['instructions'])
            content_parts.append(f"Follow-up: {follow_up_text}")
        
        # Combine all content
        document_content = " | ".join(content_parts)
        
        # If no structured content, use transcript
        if not document_content.strip():
            document_content = transcript_text[:2000]  # Limit length
        
        return document_content
    
    async def _get_patient_history(self, patient_id: str, cutoff_date: datetime) -> List[Dict[str, Any]]:
        """Get patient's historical records."""
        try:
            # Query vector database for patient records
            results = await asyncio.to_thread(
                self.collection.query,
                where={
                    "patient_id": patient_id,
                    "timestamp": {"$gte": cutoff_date.isoformat()}
                },
                n_results=50  # Limit to recent records
            )
            
            # Process results
            history = []
            if results['ids']:
                for i, record_id in enumerate(results['ids'][0]):
                    history.append({
                        'id': record_id,
                        'content': results['documents'][0][i],
                        'metadata': results['metadatas'][0][i],
                        'timestamp': results['metadatas'][0][i].get('timestamp')
                    })
            
            # Sort by timestamp (most recent first)
            history.sort(key=lambda x: x['timestamp'], reverse=True)
            
            return history
            
        except Exception as e:
            self.logger.error(f"Failed to get patient history for {patient_id}: {str(e)}")
            return []
    
    def _create_search_query(self, medical_data: Dict[str, Any]) -> str:
        """Create search query from current medical data."""
        query_parts = []
        
        if medical_data.get('symptoms'):
            query_parts.extend(medical_data['symptoms'])
        
        if medical_data.get('diagnosis'):
            query_parts.extend(medical_data['diagnosis'])
        
        return " ".join(query_parts[:5])  # Limit query length
    
    def _extract_medication_history(self, patient_history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract medication history from patient records."""
        medications = []
        
        for record in patient_history:
            metadata = record.get('metadata', {})
            if metadata.get('has_medications'):
                # Extract medications from content
                content = record.get('content', '')
                if 'Medications:' in content:
                    med_section = content.split('Medications:')[1].split('|')[0].strip()
                    medications.append({
                        'medications': med_section,
                        'date': metadata.get('timestamp'),
                        'record_id': record.get('id')
                    })
        
        return medications[:10]  # Return recent 10
    
    def _extract_chronic_conditions(self, patient_history: List[Dict[str, Any]]) -> List[str]:
        """Extract chronic conditions from patient history."""
        chronic_keywords = [
            'diabetes', 'hypertension', 'asthma', 'copd', 'arthritis',
            'depression', 'anxiety', 'heart disease', 'chronic'
        ]
        
        conditions = set()
        
        for record in patient_history:
            content = record.get('content', '').lower()
            for keyword in chronic_keywords:
                if keyword in content:
                    conditions.add(keyword.title())
        
        return list(conditions)
    
    def _extract_allergies(self, patient_history: List[Dict[str, Any]]) -> List[str]:
        """Extract known allergies from patient history."""
        allergies = []
        allergy_keywords = ['allergic to', 'allergy', 'allergies', 'adverse reaction']
        
        for record in patient_history:
            content = record.get('content', '').lower()
            if any(keyword in content for keyword in allergy_keywords):
                # Simple extraction - in production, use more sophisticated NLP
                allergies.append(f"Mentioned in consultation on {record.get('metadata', {}).get('timestamp', 'unknown date')}")
        
        return allergies[:5]  # Return recent 5
    
    def _generate_patient_summary(
        self, 
        patient_history: List[Dict[str, Any]], 
        medication_history: List[Dict[str, Any]], 
        chronic_conditions: List[str]
    ) -> str:
        """Generate a concise patient summary."""
        summary_parts = []
        
        # Basic stats
        consultation_count = len(patient_history)
        if consultation_count > 0:
            summary_parts.append(f"Patient has {consultation_count} consultations on record")
        
        # Chronic conditions
        if chronic_conditions:
            summary_parts.append(f"Known conditions: {', '.join(chronic_conditions)}")
        
        # Recent medication use
        if medication_history:
            summary_parts.append(f"Recent medications documented in {len(medication_history)} consultations")
        
        # Recent consultation frequency
        if consultation_count > 1:
            recent_consultations = [
                r for r in patient_history 
                if r.get('metadata', {}).get('timestamp') and 
                datetime.fromisoformat(r['metadata']['timestamp']) > datetime.now() - timedelta(days=90)
            ]
            if recent_consultations:
                summary_parts.append(f"{len(recent_consultations)} consultations in last 90 days")
        
        return ". ".join(summary_parts) + "." if summary_parts else "No significant medical history available."
    
    def _identify_risk_factors(self, patient_history: List[Dict[str, Any]]) -> List[str]:
        """Identify potential risk factors from patient history."""
        risk_factors = []
        
        # High consultation frequency
        recent_count = len([
            r for r in patient_history 
            if r.get('metadata', {}).get('timestamp') and 
            datetime.fromisoformat(r['metadata']['timestamp']) > datetime.now() - timedelta(days=30)
        ])
        
        if recent_count >= 3:
            risk_factors.append("High consultation frequency (3+ in last 30 days)")
        
        # Multiple medications
        medication_records = [r for r in patient_history if r.get('metadata', {}).get('has_medications')]
        if len(medication_records) >= 5:
            risk_factors.append("Multiple medication prescriptions")
        
        return risk_factors
    
    async def health_check(self) -> str:
        """Check vector database health."""
        try:
            # Simple query to test connectivity
            await asyncio.to_thread(self.collection.count)
            return "healthy"
        except Exception:
            return "unhealthy"