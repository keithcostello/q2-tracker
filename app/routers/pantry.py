"""Pantry API endpoints."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth import verify_api_token
from app.models import Pantry

router = APIRouter(prefix="/api/pantry", dependencies=[Depends(verify_api_token)])


# --- Pydantic Schemas ---

class PantryItemOut(BaseModel):
    id: int
    name: str
    category: str
    currently_stocked: bool
    last_updated: datetime


class PantryBulkUpdate(BaseModel):
    items: list[dict]  # [{"name": "apples", "currently_stocked": true}, ...]


# --- Endpoints ---

@router.get("", response_model=list[PantryItemOut])
async def list_pantry(
    category: Optional[str] = None,
    stocked_only: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """List all pantry items with stocked status."""
    q = select(Pantry)
    if category:
        q = q.where(Pantry.category == category)
    if stocked_only:
        q = q.where(Pantry.currently_stocked.is_(True))
    q = q.order_by(Pantry.category, Pantry.name)
    result = await db.execute(q)
    return result.scalars().all()


@router.put("")
async def update_pantry(data: PantryBulkUpdate, db: AsyncSession = Depends(get_db)):
    """Bulk update stocked items (after shopping)."""
    updated = []
    for item_data in data.items:
        name = item_data.get("name")
        if not name:
            continue

        result = await db.execute(select(Pantry).where(Pantry.name == name))
        pantry_item = result.scalar_one_or_none()

        if pantry_item is None:
            # Create new pantry item
            pantry_item = Pantry(
                name=name,
                category=item_data.get("category", "fruit"),
                currently_stocked=item_data.get("currently_stocked", True),
                last_updated=datetime.utcnow(),
            )
            db.add(pantry_item)
        else:
            # Update existing
            if "currently_stocked" in item_data:
                pantry_item.currently_stocked = item_data["currently_stocked"]
            if "category" in item_data:
                pantry_item.category = item_data["category"]
            pantry_item.last_updated = datetime.utcnow()

        updated.append(name)

    await db.commit()
    return {"updated": updated, "count": len(updated)}
