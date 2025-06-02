from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional


@dataclass
class AppState:
    """Holds runtime state for the Flask application."""

    login_attempts: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    last_shot: Optional[str] = None
    last_time: Optional[float] = None
    active_groups: List[str] = field(default_factory=list)
    rtsp_sessions: Dict[str, Dict[str, Any]] = field(default_factory=dict)
