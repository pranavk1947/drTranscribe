"""
Forms module for DrTranscribe.

Handles prescription generation, form templates, and validation.
"""

from .prescription.generator import PrescriptionGenerator
from .templates.form_templates import FormTemplateManager
from .validators.form_validator import FormValidator

__all__ = ["PrescriptionGenerator", "FormTemplateManager", "FormValidator"]