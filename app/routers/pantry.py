"""Pantry API endpoints."""

import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth import verify_api_token, verify_write_token
from app.models import Pantry, now_pacific

PACIFIC = ZoneInfo("America/Los_Angeles")

router = APIRouter(prefix="/api/pantry")


# --- Load Schedule Config from JSON ---

_ROUTER_DIR = os.path.dirname(os.path.abspath(__file__))
_APP_DIR = os.path.dirname(_ROUTER_DIR)
_PROJECT_DIR = os.path.dirname(_APP_DIR)
_CONFIG_PATH = os.path.join(_PROJECT_DIR, "schedule_config.json")

with open(_CONFIG_PATH, "r") as _f:
    SCHEDULE_CONFIG = json.load(_f)


# --- Pydantic Schemas ---

class PantryItemOut(BaseModel):
    id: int
    name: str
    category: str
    currently_stocked: bool
    last_updated: datetime


class PantryBulkUpdate(BaseModel):
    items: list[dict]


class PantrySeededResponse(BaseModel):
    created_count: int
    items: list[dict]


# --- Read Endpoints (accept read or write token) ---

@router.get("", response_model=list[PantryItemOut], dependencies=[Depends(verify_api_token)])
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


# --- Write Endpoints (require write token) ---

@router.post("/seed", response_model=PantrySeededResponse, dependencies=[Depends(verify_write_token)])
async def seed_pantry(db: AsyncSession = Depends(get_db)):
    """Seed the pantry table from food_choice_options in schedule_config.json."""
    food_choice_options = SCHEDULE_CONFIG.get("food_choice_options", {})

    fruit_lists = ["oatmeal_fruits", "snack_fruits", "pre_workout_fruits"]
    veg_lists = ["veggie_bowl_vegetables", "snack_vegetables"]

    items_dict = {}

    for list_key in fruit_lists:
        list_data = food_choice_options.get(list_key, {})
        master_list = list_data.get("master_list", [])
        for item in master_list:
            normalized = item.lower().strip()
            if normalized not in items_dict:
                items_dict[normalized] = {"name": item, "category": "fruit"}

    for list_key in veg_lists:
        list_data = food_choice_options.get(list_key, {})
        master_list = list_data.get("master_list", [])
        for item in master_list:
            normalized = item.lower().strip()
            if normalized not in items_dict:
                items_dict[normalized] = {"name": item, "category": "vegetable"}

    created_items = []
    for normalized_name, item_info in items_dict.items():
        original_name = item_info["name"]
        category = item_info["category"]

        result = await db.execute(select(Pantry).where(Pantry.name == original_name))
        existing = result.scalar_one_or_none()

        if existing is None:
            pantry_item = Pantry(
                name=original_name,
                category=category,
                currently_stocked=False,
                last_updated=now_pacific(),
            )
            db.add(pantry_item)
            created_items.append({"name": original_name, "category": category})

    await db.commit()

    return {
        "created_count": len(created_items),
        "items": created_items,
    }


@router.put("", dependencies=[Depends(verify_write_token)])
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
            pantry_item = Pantry(
                name=name,
                category=item_data.get("category", "fruit"),
                currently_stocked=item_data.get("currently_stocked", True),
                last_updated=now_pacific(),
            )
            db.add(pantry_item)
        else:
            if "currently_stocked" in item_data:
                pantry_item.currently_stocked = item_data["currently_stocked"]
            if "category" in item_data:
                pantry_item.category = item_data["category"]
            pantry_item.last_updated = now_pacific()

        updated.append(name)

    await db.commit()
    return {"updated": updated, "count": len(updated)}
