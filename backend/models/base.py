"""SQLAlchemy declarative base for all models."""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models.
    
    Usage:
        from backend.models.base import Base
        
        class User(Base):
            __tablename__ = "users"
            id: Mapped[str] = mapped_column(primary_key=True)
    """
    pass
---