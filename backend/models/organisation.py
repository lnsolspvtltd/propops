from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
import logging

logger = logging.getLogger(__name__)

class Organisation(Base):
    __tablename__ = "organisations"
    
    id: Mapped[str] = mapped_column(primary_key=True)
    name: str = mapped_column(String(255), nullable=False)
    imap_host: str | None = mapped_column(String(255))
    imap_port: int = mapped_column(Integer, default=993)
    imap_username: str | None = mapped_column(String(255))
    imap_password_enc: str | None = mapped_column(String(255))  # Fernet encrypted
    smtp_host: str | None = mapped_column(String(255))
    smtp_port: int = mapped_column(Integer, default=587)
    polling_active: bool = mapped_column(Boolean, default=False)
    created_at: Mapped[DateTime] = mapped_column(default=DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(default=DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))

    # Indexes
    __table_args__ = (
        Index("idx_organisations_deleted", deleted_at),
    )

    def __repr__(self):
        return f"<Organisation(id={self.id}, name={self.name})>"