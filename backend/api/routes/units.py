from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_db
from backend.models import Unit

router = APIRouter(prefix="/api/v1", tags=["units"])

class UnitCreate(BaseModel):
    label: str
    address: str

@router.get("/units")
async def list_units(db: AsyncSession = Depends(get_db)):
    units = await db.execute(select(Unit).filter_by(deleted_at=None))
    return {"units": [unit.model_dump() for unit in units.scalars().all()]}

@router.post("/units")
async def create_unit(unit_data: UnitCreate, db: AsyncSession = Depends(get_db)):
    try:
        unit = Unit(
            label=unit_data.label,
            address=unit_data.address
        )
        db.add(unit)
        await db.commit()
        await db.refresh(unit)

        return {"id": unit.id, "label": unit.label}
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))