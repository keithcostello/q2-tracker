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
from app.auth import verify_api_token
from app.models import Pantry

PACIFIC = ZoneInfo("America/Los_Angeles")

router = APIRouter(prefix="/api/pantry", dependencies=[Depends(verify_api_token)])


# --- Load Schedule Config from JSON ---

_ROUTER_DIR = os.path.dirname(os.path.abspath(__file__))       # app/routers/
_APP_DIR = os.path.dirname(_ROUTER_DIR)                        # app/
_PROJECT_DIR = os.path.dirname(_APP_DIR)                       # q2-tracker-backend/
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
    items: list[dict]  # [{"name": "apples", "currently_stocked": true}, ...]


class PantrySeededResponse(BaseModel):
    created_count: int
    items: list[dict]  # [{"name": "apples", "category": "fruit"}, ...]


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


@router.post("/seed", response_model=PantrySeededResponse)
async def seed_pantry(db: AsyncSession = Depends(get_db)):
    """Seed the pantry table from food_choice_options in schedule_config.json.

    - Reads all 5 food choice lists: oatmeal_fruits, veggie_bowl_vegetables, snack_vegetables, snack_fruits, pre_workout_fruits
    - Deduplicates items across all lists
    - Categorizes each as "fruit" or "vegetable" based on which list(s) it appears in
    - Creates Pantry records for each unique item (skips if already exists)
    - Sets currently_stocked to False (user updates after shopping)

    Returns: count of items created and list of all items (including duplicates)
    """
    food_choice_options = SCHEDULE_CONFIG.get("food_choice_options", {})

    # Fruit lists
    fruit_lists = ["oatmeal_fruits", "snack_fruits", "pre_workout_fruits"]
    # Vegetable lists
    veg_lists = ["veggie_bowl_vegetables", "snack_vegetables"]

    # Track items by category: normalize names and deduplicate within each category
    items_dict = {}  # {normalized_name: {"name": original_name, "category": "fruit"|"vegetable"}}

    # Process fruit lists
    for list_key in fruit_lists:
        list_data = food_choice_options.get(list_key, {})
        master_list = list_data.get("master_list", [])
        for item in master_list:
            normalized = item.lower().strip()
            if normalized not in items_dict:
                items_dict[normalized] = {"name": item, "category": "fruit"}

    # Process vegetable lists
    for list_key in veg_lists:
        list_data = food_choice_options.get(list_key, {})
        master_list = list_data.get("master_list", [])
        for item in master_list:
            normalized = item.lower().strip()
            if normalized not in items_dict:
                items_dict[normalized] = {"name": item, "category": "vegetable"}

    # Now insert into database, skipping duplicates
    created_items = []
    for normalized_name, item_info in items_dict.items():
        original_name = item_info["name"]
        category = item_info["category"]

        # Check if item already exists
        result = await db.execute(select(Pantry).where(Pantry.name == original_name))
        existing = result.scalar_one_or_none()

        if existing is None:
            # Create new pantry item
            pantry_item = Pantry(
                name=original_name,
                category=category,
                currently_stocked=False,
                last_updated=datetime.now(PACIFIC),
            )
            db.add(pantry_item)
            created_items.append({"name": original_name, "category": category})

    await db.commit()

    return {
        "created_count": len(created_items),
        "items": created_items,
    }


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
                last_updated=datetime.now(PACIFIC),
            )
            db.add(pantry_item)
        else:
            # Update existing
            if "currently_stocked" in item_data:
                pantry_item.currently_stocked = item_data["currently_stocked"]
            if "category" in item_data:
                pantry_item.category = item_data["category"]
            pantry_item.last_updated = datetime.now(PACIFIC)

        updated.append(name)

    await db.commit()
    return {"updated": updated, "count": len(updated)}
