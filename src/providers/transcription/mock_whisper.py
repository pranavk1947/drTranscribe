import logging
import asyncio
from ..base import TranscriptionProvider

logger = logging.getLogger(__name__)


class MockWhisperProvider(TranscriptionProvider):
    """Mock transcription provider for testing without Whisper API."""
    
    def __init__(self, **kwargs):
        self.counter = 0
        logger.info("⚠️  Using MOCK transcription (simulated audio-to-text)")
        logger.info("   Real transcription requires Whisper deployment in Azure")
    
    async def transcribe(self, audio_bytes: bytes) -> str:
        """Simulate transcription with realistic medical conversation."""
        await asyncio.sleep(0.5)
        
        # Rotate through realistic medical consultation dialogue
        responses = [
            "Doctor: Hello, how can I help you today? Patient: I've been having severe headaches for the past week.",
            "Patient: The pain is really intense, about 8 out of 10. Doctor: I see, that's quite severe. Can you describe the pain?",
            "Patient: It's a throbbing pain mostly on the left side. Doctor: Based on your symptoms, I believe you're experiencing tension headaches, possibly stress-related.",
            "Doctor: I'm going to prescribe Ibuprofen 400 milligrams. Take it twice daily with food. Patient: Okay, thank you doctor.",
            "Doctor: I'd also advise you to reduce screen time, take regular breaks every hour, and practice relaxation techniques like deep breathing.",
            "Patient: Is there anything else I should do? Doctor: Yes, I'd like you to get a blood test done to check for any vitamin deficiencies, and come back in two weeks for a follow-up appointment.",
        ]
        
        response = responses[self.counter % len(responses)]
        self.counter += 1
        
        logger.info(f"📝 Mock transcription #{self.counter}: {response[:60]}...")
        return response
