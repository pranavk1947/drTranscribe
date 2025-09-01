"""
Medical entity extraction from clinical text using specialized NLP models.
"""

import asyncio
import logging
from typing import Dict, Any, List, Tuple
import spacy
from transformers import AutoTokenizer, AutoModelForTokenClassification, pipeline
import re

from ...config.settings import Config


class MedicalEntityExtractor:
    """Extract medical entities from clinical text using multiple NLP approaches."""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self._load_models()
    
    def _load_models(self):
        """Load medical NLP models for entity extraction."""
        try:
            # Load spaCy medical model if available
            try:
                self.nlp = spacy.load("en_core_sci_sm")
                self.logger.info("Loaded SciSpaCy medical model")
            except OSError:
                self.nlp = spacy.load("en_core_web_sm")
                self.logger.warning("SciSpaCy not available, using standard English model")
            
            # Load medical NER model
            self.medical_tokenizer = AutoTokenizer.from_pretrained(
                self.config.medical_nlp.entity_extraction_model
            )
            self.medical_model = AutoModelForTokenClassification.from_pretrained(
                self.config.medical_nlp.entity_extraction_model
            )
            
            # Create NER pipeline
            self.ner_pipeline = pipeline(
                "ner",
                model=self.medical_model,
                tokenizer=self.medical_tokenizer,
                aggregation_strategy="simple",
                device=-1  # CPU
            )
            
            self.logger.info("Medical entity extraction models loaded successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to load medical NLP models: {str(e)}")
            raise
    
    async def extract_entities(self, text: str) -> Dict[str, List[Dict]]:
        """
        Extract medical entities from text using multiple approaches.
        
        Args:
            text: Clinical text to analyze
            
        Returns:
            Dictionary of extracted entities by category
        """
        try:
            # Run different extraction methods concurrently
            tasks = [
                self._extract_with_transformer(text),
                self._extract_with_spacy(text),
                self._extract_with_regex_patterns(text)
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Merge results from different methods
            transformer_entities = results[0] if not isinstance(results[0], Exception) else {}
            spacy_entities = results[1] if not isinstance(results[1], Exception) else {}
            regex_entities = results[2] if not isinstance(results[2], Exception) else {}
            
            # Combine and deduplicate entities
            combined_entities = self._merge_entity_results(
                transformer_entities, spacy_entities, regex_entities
            )
            
            return combined_entities
            
        except Exception as e:
            self.logger.error(f"Entity extraction failed: {str(e)}")
            return {}
    
    async def _extract_with_transformer(self, text: str) -> Dict[str, List[Dict]]:
        """Extract entities using transformer-based NER model."""
        try:
            # Run NER pipeline
            ner_results = await asyncio.to_thread(self.ner_pipeline, text)
            
            entities = {
                'symptoms': [],
                'conditions': [],
                'medications': [],
                'anatomical_parts': [],
                'procedures': [],
                'lab_values': []
            }
            
            for entity in ner_results:
                entity_info = {
                    'text': entity['word'],
                    'label': entity['entity_group'],
                    'confidence': entity['score'],
                    'start': entity['start'],
                    'end': entity['end'],
                    'method': 'transformer'
                }
                
                # Map entity labels to categories
                category = self._map_entity_to_category(entity['entity_group'])
                if category:
                    entities[category].append(entity_info)
            
            return entities
            
        except Exception as e:
            self.logger.error(f"Transformer entity extraction failed: {str(e)}")
            return {}
    
    async def _extract_with_spacy(self, text: str) -> Dict[str, List[Dict]]:
        """Extract entities using spaCy medical model."""
        try:
            doc = await asyncio.to_thread(self.nlp, text)
            
            entities = {
                'symptoms': [],
                'conditions': [],
                'medications': [],
                'anatomical_parts': [],
                'procedures': [],
                'lab_values': []
            }
            
            for ent in doc.ents:
                entity_info = {
                    'text': ent.text,
                    'label': ent.label_,
                    'confidence': 0.9,  # spaCy doesn't provide confidence scores
                    'start': ent.start_char,
                    'end': ent.end_char,
                    'method': 'spacy'
                }
                
                # Map spaCy labels to our categories
                category = self._map_spacy_label_to_category(ent.label_)
                if category:
                    entities[category].append(entity_info)
            
            return entities
            
        except Exception as e:
            self.logger.error(f"spaCy entity extraction failed: {str(e)}")
            return {}
    
    async def _extract_with_regex_patterns(self, text: str) -> Dict[str, List[Dict]]:
        """Extract entities using regex patterns for medical concepts."""
        entities = {
            'symptoms': [],
            'conditions': [],
            'medications': [],
            'anatomical_parts': [],
            'procedures': [],
            'lab_values': []
        }
        
        # Define regex patterns for medical entities
        patterns = {
            'medications': [
                r'\b\w+(?:cillin|mycin|prazole|statin|sartan)\b',  # Common drug suffixes
                r'\b(?:mg|ml|units?)\b',  # Dosage indicators
            ],
            'lab_values': [
                r'\b(?:blood pressure|BP):?\s*\d+/\d+',
                r'\b(?:heart rate|HR):?\s*\d+',
                r'\b(?:temperature|temp):?\s*\d+\.?\d*',
                r'\b\d+\.?\d*\s*(?:mg/dL|mmol/L|%)',  # Lab measurements
            ],
            'procedures': [
                r'\b(?:X-ray|CT scan|MRI|ultrasound|biopsy|surgery)\b',
                r'\b(?:injection|vaccination|examination)\b',
            ],
            'anatomical_parts': [
                r'\b(?:heart|lung|liver|kidney|brain|stomach|chest|head|neck|back|arm|leg)\b',
            ]
        }
        
        for category, category_patterns in patterns.items():
            for pattern in category_patterns:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    entity_info = {
                        'text': match.group(),
                        'label': f'REGEX_{category.upper()}',
                        'confidence': 0.7,
                        'start': match.start(),
                        'end': match.end(),
                        'method': 'regex'
                    }
                    entities[category].append(entity_info)
        
        return entities
    
    def _map_entity_to_category(self, entity_label: str) -> str:
        """Map transformer entity labels to our categories."""
        label_mapping = {
            'DISEASE': 'conditions',
            'SYMPTOM': 'symptoms',
            'MEDICATION': 'medications',
            'ANATOMY': 'anatomical_parts',
            'PROCEDURE': 'procedures',
            'TEST': 'lab_values'
        }
        
        return label_mapping.get(entity_label.upper(), None)
    
    def _map_spacy_label_to_category(self, spacy_label: str) -> str:
        """Map spaCy entity labels to our categories."""
        label_mapping = {
            'DISEASE': 'conditions',
            'SYMPTOM': 'symptoms',
            'CHEMICAL': 'medications',
            'ANATOMY': 'anatomical_parts',
            'PROCEDURE': 'procedures',
        }
        
        return label_mapping.get(spacy_label, None)
    
    def _merge_entity_results(self, *entity_dicts) -> Dict[str, List[Dict]]:
        """Merge and deduplicate entity results from different methods."""
        merged = {
            'symptoms': [],
            'conditions': [],
            'medications': [],
            'anatomical_parts': [],
            'procedures': [],
            'lab_values': []
        }
        
        for entity_dict in entity_dicts:
            if not entity_dict:
                continue
                
            for category, entities in entity_dict.items():
                if category in merged:
                    merged[category].extend(entities)
        
        # Deduplicate entities based on text and position
        for category in merged:
            merged[category] = self._deduplicate_entities(merged[category])
            # Sort by confidence score
            merged[category].sort(key=lambda x: x['confidence'], reverse=True)
        
        return merged
    
    def _deduplicate_entities(self, entities: List[Dict]) -> List[Dict]:
        """Remove duplicate entities based on text overlap."""
        deduplicated = []
        
        for entity in entities:
            is_duplicate = False
            for existing in deduplicated:
                # Check for text overlap
                if (self._has_significant_overlap(entity['text'], existing['text']) and 
                    abs(entity['start'] - existing['start']) < 5):
                    # Keep the one with higher confidence
                    if entity['confidence'] > existing['confidence']:
                        deduplicated.remove(existing)
                        deduplicated.append(entity)
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                deduplicated.append(entity)
        
        return deduplicated
    
    def _has_significant_overlap(self, text1: str, text2: str) -> bool:
        """Check if two text strings have significant overlap."""
        text1_words = set(text1.lower().split())
        text2_words = set(text2.lower().split())
        
        if not text1_words or not text2_words:
            return False
        
        intersection = text1_words.intersection(text2_words)
        union = text1_words.union(text2_words)
        
        # Jaccard similarity > 0.5 indicates significant overlap
        return len(intersection) / len(union) > 0.5