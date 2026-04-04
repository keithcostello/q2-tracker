"""Daily Runsheet API endpoints."""

import json
import os
import logging
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.auth import verify_api_token
from app.models import (
    DailyPlan, PlanItem, FoodChoice,
    PlanStatus, ItemStatus, ItemCategory, ChoiceType,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/runsheet", dependencies=[Depends(verify_api_token)])


# --- Load Schedule Config from JSON ---

def _find_config() -> str:
    """Try multiple paths to find schedule_config.json."""
    candidates = [
        # Path relative to this file: app/routers/ -> app/ -> repo root
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "schedule_config.json"),
        # Path relative to cwd (Railway typically runs from repo root)
        os.path.join(os.getcwd(), "schedule_config.json"),
        # Absolute fallback for nixpacks
        "/app/schedule_config.json",
    ]
    for path in candidates:
        logger.info(f"Checking config path: {path} -> exists={os.path.exists(path)}")
        if os.path.isfile(path):
            logger.info(f"Found schedule_config.json at: {path}")
            return path
    cwd = os.getcwd()
    logger.error(f"schedule_config.json not found. cwd={cwd}")
    try:
        logger.error(f"cwd contents: {os.listdir(cwd)}")
    except Exception:
        pass
    raise FileNotFoundError(f"schedule_config.json not found. Tried: {candidates}")


_CONFIG_PATH = _find_config()
with open(_CONFIG_PATH, "r") as _f:
    SCHEDULE_CONFIG = json.load(_f)

SYSTEM_START_DATE = date.fromisoformat(SCHEDULE_CONFIG["meta"]["system_start_date"])

# Map weekday index (0=Mon) to JSON key
_WEEKDAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def get_week_number(d: date) -> int:
    """Return 1 or 2 for two-week rotation, anchored to system start date (2026-03-16).

    Weeks 0, 2, 4… from start = Week 1.  Weeks 1, 3, 5… = Week 2.
    """
    days_since_start = (d - SYSTEM_START_DATE).days
    return 1 if (days_since_start // 7) % 2 == 0 else 2


def get_day_type(d: date) -> str:
    """Get a human-readable day type string from schedule_config.json."""
    day_name = _WEEKDAY_NAMES[d.weekday()]
    template = SCHEDULE_CONFIG["day_templates"].get(day_name, {})
    title = template.get("title", day_name.capitalize())
    return f"{day_name.capitalize()} — {title}"


def get_day_items(d: date) -> list[dict]:
    """Return the ordered item list for a given date from schedule_config.json."""
    day_name = _WEEKDAY_NAMES[d.weekday()]
    template = SCHEDULE_CONFIG["day_templates"].get(day_name, {})
    return template.get("items", [])


async def auto_generate_plan(d: date, db: AsyncSession) -> DailyPlan:
    """Generate a daily plan from schedule_config.json for the given date."""
    day_type = get_day_type(d)
    week_number = get_week_number(d)

    plan = DailyPlan(
        date=d,
        day_type=day_type,
        week_number=week_number,
        status=PlanStatus.ACTIVE.value,
    )
    db.add(plan)
    await db.flush()

    items_template = get_day_items(d)
    for cfg_item in items_template:
        item = PlanItem(
            plan_id=plan.id,
            order=cfg_item["order"],
            label=cfg_item["label"],
            category=cfg_item["category"],
            status=ItemStatus.PENDING.value,
        )
        db.add(item)
        await db.flush()  # Need the item.id for FoodChoice

        # Create FoodChoice if this item has a food_choice_type
        if "food_choice_type" in cfg_item:
            choice = FoodChoice(
                plan_item_id=item.id,
                choice_type=cfg_item["food_choice_type"],
                selected=None,
                options={"multi_select": cfg_item.get("multi_select", False)},
            )
            db.add(choice)
            await db.flush()
            item.food_choice_id = choice.id

    await db.commit()

    # Reload with relationships
    result = await db.execute(
        select(DailyPlan)
        .options(selectinload(DailyPlan.items).selectinload(PlanItem.food_choice))
        .where(DailyPlan.id == plan.id)
    )
    return result.scalar_one()


# --- Pydantic Schemas ---

class FoodChoiceOut(BaseModel):
    id: int
    plan_item_id: int
    choice_type: str
    selected: Optional[str]
    options: Optional[dict]


class PlanItemOut(BaseModel):
    id: int
    plan_id: int
    order: int
    label: str
    status: str
    category: str
    food_choice_id: Optional[int]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    food_choice: Optional[FoodChoiceOut] = None


class DailyPlanOut(BaseModel):
    id: int
    date: date
    day_type: str
    week_number: int
    custom_edits: Optional[dict]
    status: str
    items: list[PlanItemOut]


class EditAction(BaseModel):
    action: str  # "add", "delete", "reorder"
    item_id: Optional[int] = None
    label: Optional[str] = None
    category: Optional[str] = None
    new_order: Optional[list[int]] = None


class FoodChoiceIn(BaseModel):
    plan_item_id: int
    choice_type: ChoiceType
    selected: str
    options: Optional[dict] = None


# --- Endpoints ---

@router.get("/today", response_model=DailyPlanOut)
async def get_today(db: AsyncSession = Depends(get_db)):
    """Return today's plan. Auto-generate if none exists."""
    today = date.today()
    result = await db.execute(
        select(DailyPlan)
        .options(selectinload(DailyPlan.items).selectinload(PlanItem.food_choice))
        .where(DailyPlan.date == today)
    )
    plan = result.scalar_one_or_none()

    if plan is None:
        plan = await auto_generate_plan(today, db)

    return plan


@router.post("/item/{item_id}/complete")
async def complete_item(item_id: int, db: AsyncSession = Depends(get_db)):
    """Mark a plan item as done."""
    result = await db.execute(select(PlanItem).where(PlanItem.id == item_id))
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")

    item.status = ItemStatus.DONE.value
    item.completed_at = datetime.utcnow()
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "status": item.status, "completed_at": item.completed_at.isoformat()}


@router.post("/item/{item_id}/skip")
async def skip_item(item_id: int, db: AsyncSession = Depends(get_db)):
    """Mark a plan item as skipped."""
    result = await db.execute(select(PlanItem).where(PlanItem.id == item_id))
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")

    item.status = ItemStatus.SKIPPED.value
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "status": item.status}


@router.post("/edit")
async def edit_plan(edits: list[EditAction], db: AsyncSession = Depends(get_db)):
    """Add, delete, or reorder items in today's plan."""
    today = date.today()
    result = await db.execute(
        select(DailyPlan)
        .options(selectinload(DailyPlan.items))
        .where(DailyPlan.date == today)
    )
    plan = result.scalar_one_or_none()
    if plan is None:
        raise HTTPException(status_code=404, detail="No plan for today")

    results = []
    for edit in edits:
        if edit.action == "add":
            if not edit.label or not edit.category:
                raise HTTPException(status_code=422, detail="Add requires label and category")
            max_order = max((i.order for i in plan.items), default=0)
            new_item = PlanItem(
                plan_id=plan.id,
                order=max_order + 1,
                label=edit.label,
                category=edit.category,
                status=ItemStatus.PENDING.value,
            )
            db.add(new_item)
            await db.flush()
            results.append({"action": "added", "item_id": new_item.id})

        elif edit.action == "delete":
            if not edit.item_id:
                raise HTTPException(status_code=422, detail="Delete requires item_id")
            item_result = await db.execute(
                select(PlanItem).where(PlanItem.id == edit.item_id, PlanItem.plan_id == plan.id)
            )
            item = item_result.scalar_one_or_none()
            if item is None:
                raise HTTPException(status_code=404, detail=f"Item {edit.item_id} not found")
            await db.delete(item)
            results.append({"action": "deleted", "item_id": edit.item_id})

        elif edit.action == "reorder":
            if not edit.new_order:
                raise HTTPException(status_code=422, detail="Reorder requires new_order")
            for position, item_id in enumerate(edit.new_order, 1):
                item_result = await db.execute(
                    select(PlanItem).where(PlanItem.id == item_id, PlanItem.plan_id == plan.id)
                )
                item = item_result.scalar_one_or_none()
                if item:
                    item.order = position
            results.append({"action": "reordered"})

        else:
            raise HTTPException(status_code=422, detail=f"Unknown action: {edit.action}")

    # Store edits in custom_edits JSON
    existing_edits = plan.custom_edits or {"additions": [], "deletions": [], "reorders": []}
    for edit in edits:
        if edit.action == "add":
            existing_edits.setdefault("additions", []).append(edit.label)
        elif edit.action == "delete":
            existing_edits.setdefault("deletions", []).append(edit.item_id)
        elif edit.action == "reorder":
            existing_edits["reorders"] = edit.new_order
    plan.custom_edits = existing_edits

    await db.commit()
    return {"edits": results}


@router.post("/food-choice", status_code=201)
async def record_food_choice(data: FoodChoiceIn, db: AsyncSession = Depends(get_db)):
    """Record a food selection for a plan item.

    If a FoodChoice already exists for this plan item (e.g. auto-generated),
    update it in place rather than creating a duplicate.
    """
    result = await db.execute(select(PlanItem).where(PlanItem.id == data.plan_item_id))
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Plan item not found")

    # Check for existing FoodChoice (auto-generated plans create one with selected=None)
    existing_result = await db.execute(
        select(FoodChoice).where(FoodChoice.plan_item_id == data.plan_item_id)
    )
    existing_choice = existing_result.scalar_one_or_none()

    if existing_choice is not None:
        # Update existing choice
        existing_choice.choice_type = data.choice_type.value
        existing_choice.selected = data.selected
        if data.options is not None:
            existing_choice.options = data.options
        choice = existing_choice
    else:
        # Create new choice
        choice = FoodChoice(
            plan_item_id=data.plan_item_id,
            choice_type=data.choice_type.value,
            selected=data.selected,
            options=data.options,
        )
        db.add(choice)
        await db.flush()
        item.food_choice_id = choice.id

    await db.commit()
    await db.refresh(choice)

    return {
        "id": choice.id,
        "plan_item_id": choice.plan_item_id,
        "choice_type": choice.choice_type,
        "selected": choice.selected,
        "options": choice.options,
    }
