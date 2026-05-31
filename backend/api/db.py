"""Re-export get_db from core.database for route compatibility."""
from backend.core.database import get_db  # noqa: F401

__all__ = ["get_db"]
