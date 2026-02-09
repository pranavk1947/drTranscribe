import logging
from typing import Dict, Optional
from ..models.consultation import ConsultationSession

logger = logging.getLogger(__name__)


class SessionManager:
    """In-memory session management."""
    
    def __init__(self):
        self.sessions: Dict[str, ConsultationSession] = {}
        logger.info("Session manager initialized")
    
    def create_session(self, session: ConsultationSession) -> ConsultationSession:
        """Create a new session."""
        self.sessions[session.session_id] = session
        logger.info(f"Created session: {session.session_id}")
        return session
    
    def get_session(self, session_id: str) -> Optional[ConsultationSession]:
        """Get a session by ID."""
        return self.sessions.get(session_id)
    
    def end_session(self, session_id: str) -> None:
        """End and remove a session."""
        if session_id in self.sessions:
            del self.sessions[session_id]
            logger.info(f"Ended session: {session_id}")
    
    def get_active_sessions_count(self) -> int:
        """Get the number of active sessions."""
        return len(self.sessions)
