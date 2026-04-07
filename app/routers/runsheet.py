"""Daily Runsheet API endpoints."""

import json
import os
import logging
import traceback
from datetime import date, datetime
from zoneinfo import ZoneInfo
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.auth import verify_api_token, verify_write_token
from app.models import (
    DailyPlan, PlanItem, FoodChoice,
    PlanStatus, ItemStatus, ItemCategory, ChoiceType,
    now_pacific,
)

logger = logging.getLogger(__name__)

PACIFIC = ZoneInfo("America/Los_Angeles")

router = APIRouter(prefix="/api/runsheet")


# --- Load Schedule Config from JSON ---

def _find_config() -> str:
    """Try multiple paths to find schedule_config.json."""
    candidates = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "schedule_config.json"),
        os.path.join(os.getcwd(), "schedule_config.json"),
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

_WEEKDAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def get_week_number(d: date) -> int:
    days_since_start = (d - SYSTEM_START_DATE).days
    return 1 if (days_since_start // 7) % 2 == 0 else 2


def get_day_type(d: date) -> str:
    day_name = _WEEKDAY_NAMES[d.weekday()]
    template = SCHEDULE_CONFIG["day_templates"].get(day_name, {})
    title = template.get("title", day_name.capitalize())
    return f"{day_name.capitalize()} \u2014 {title}"


def get_day_items(d: date) -> list[dict]:
    day_name = _WEEKDAY_NAMES[d.weekday()]
    template = SCHEDULE_CONFIG["day_templates"].get(day_name, {})
    return template.get("items", [])


def get_dinner_info(d: date) -> dict:
    day_name = _WEEKDAY_NAMES[d.weekday()]
    week_key = f"week_{get_week_number(d)}"
    return SCHEDULE_CONFIG.get("dinner_rotation", {}).get(week_key, {}).get(day_name, {})


async def auto_generate_plan(d: date, db: AsyncSession) -> DailyPlan:
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

    dinner_info = get_dinner_info(d)

    items_template = get_day_items(d)
    for cfg_item in items_template:
        label = cfg_item["label"]

        if label == "Dinner" and dinner_info:
            label = f"Dinner \u2014 {dinner_info['name']}"
        elif label == "Prep vegetables" and dinner_info:
            label = f"Prep \u2014 {dinner_info.get('ingredients', 'vegetables')}"

        item = PlanItem(
            plan_id=plan.id,
            order=cfg_item["order"],
            label=label,
            category=cfg_item["category"],
            status=ItemStatus.PENDING.value,
        )
        db.add(item)
        await db.flush()

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
    action: str
    item_id: Optional[int] = None
    label: Optional[str] = None
    category: Optional[str] = None
    new_order: Optional[list[int]] = None


class FoodChoiceIn(BaseModel):
    plan_item_id: int
    choice_type: ChoiceType
    selected: str
    options: Optional[dict] = None


# --- Read Endpoints (accept read or write token) ---

@router.get("/today", response_model=DailyPlanOut, dependencies=[Depends(verify_api_token)])
async def get_today(db: AsyncSession = Depends(get_db)):
    """Return today's plan. Auto-generate if none exists."""
    today = datetime.now(PACIFIC).date()
    result = await db.execute(
        select(DailyPlan)
        .options(selectinload(DailyPlan.items).selectinload(PlanItem.food_choice))
        .where(DailyPlan.date == today)
    )
    plan = result.scalar_one_or_none()

    if plan is None:
        plan = await auto_generate_plan(today, db)

    return plan


# --- Write Endpoints (require write token) ---

@router.post("/regenerate", dependencies=[Depends(verify_write_token)])
async def regenerate_plan(db: AsyncSession = Depends(get_db)):
    """Delete today's plan and regenerate it from schedule_config.json."""
    today = datetime.now(PACIFIC).date()
    result = await db.execute(
        select(DailyPlan)
        .options(selectinload(DailyPlan.items).selectinload(PlanItem.food_choice))
        .where(DailyPlan.date == today)
    )
    old_plan = result.scalar_one_or_none()

    if old_plan is not None:
        for item in old_plan.items:
            if item.food_choice:
                await db.delete(item.food_choice)
            await db.delete(item)
        await db.delete(old_plan)
        await db.commit()

    new_plan = await auto_generate_plan(today, db)
    return {
        "regenerated": True,
        "date": today.isoformat(),
        "plan_id": new_plan.id,
        "item_count": len(new_plan.items),
    }


@router.post("/item/{item_id}/complete", dependencies=[Depends(verify_write_token)])
async def complete_item(item_id: int, db: AsyncSession = Depends(get_db)):
    """Mark a plan item as done."""
    try:
        result = await db.execute(select(PlanItem).where(PlanItem.id == item_id))
        item = result.scalar_one_or_none()
        if item is None:
            raise HTTPException(status_code=404, detail="Item not found")

        item.status = ItemStatus.DONE.value
        item.completed_at = now_pacific()
        await db.commit()
        await db.refresh(item)
        return {"id": item.id, "status": item.status, "completed_at": item.completed_at.isoformat()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"complete_item failed: {e}")
        logger.error(traceback.format_exc())
        return JSONResponse(status_code=500, content={"detail": str(e), "traceback": traceback.format_exc()})


@router.post("/item/{item_id}/skip", dependencies=[Depends(verify_write_token)])
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


@router.post("/item/{item_id}/reset", dependencies=[Depends(verify_write_token)])
async def reset_item(item_id: int, db: AsyncSession = Depends(get_db)):
    """Reset a done or skipped item back to pending."""
    result = await db.execute(select(PlanItem).where(PlanItem.id == item_id))
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")

    item.status = ItemStatus.PENDING.value
    item.completed_at = None
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "status": item.status}


@router.post("/edit", dependencies=[Depends(verify_write_token)])
async def edit_plan(edits: list[EditAction], db: AsyncSession = Depends(get_db)):
    """Add, delete, or reorder items in today's plan."""
    today = datetime.now(PACIFIC).date()
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


@router.post("/food-choice", status_code=201, dependencies=[Depends(verify_write_token)])
async def record_food_choice(data: FoodChoiceIn, db: AsyncSession = Depends(get_db)):
    """Record a food selection for a plan item."""
    result = await db.execute(select(PlanItem).where(PlanItem.id == data.plan_item_id))
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Plan item not found")

    existing_result = await db.execute(
        select(FoodChoice).where(FoodChoice.plan_item_id == data.plan_item_id)
    )
    existing_choice = existing_result.scalar_one_or_none()

    if existing_choice is not None:
        existing_choice.choice_type = data.choice_type.value
        existing_choice.selected = data.selected
        if data.options is not None:
            existing_choice.options = data.options
        choice = existing_choice
    else:
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
