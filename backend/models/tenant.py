from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, UUID, ForeignKey, select
from sqlalchemy.ext.asyncio import AsyncSession

class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[str] = mapped_column(primary_key=True)
    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    name: Mapped[str]
    email: Mapped[str]
    phone: Mapped[str | None]
    unit_id: Mapped[UUID | None]

class Unit(Base):
    __tablename__ = "units"
    id: Mapped[str] = mapped_column(primary_key=True)
    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    label: Mapped[str]
    address: Mapped[str]