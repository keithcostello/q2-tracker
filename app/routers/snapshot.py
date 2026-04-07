"""Snapshot API — single-call data export optimized for AI analysis.

Returns all tracker data for a date range in one response.
Full detail for small tables, summarized for plan_items (token-heavy).
"""

from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, case, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.auth import verify_api_token
from app.models import (
    Spending, DefusionLog, CheckIn, AppleHealth,
    DailyPlan, PlanItem, FoodChoice, Pantry,
)

PACIFIC = ZoneInfo("America/Los_Angeles")

router = APIRouter(prefix="/api/snapshot", dependencies=[Depends(verify_api_token)])


def _default_range() -> tuple[date, date]:
    today = datetime.now(PACIFIC).date()
    return today - timedelta(days=30), today


@router.get("")
async def get_snapshot(
    start: Optional[date] = None,
    end: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
):
    """Return all tracker data for the given date range.

    Optimized for AI consumption:
    - Small tables (defusion, check-ins, spending, health): full row detail
    - Food choices: joined with plan item label for human-readable context
    - Plan items: summarized as daily completion counts by category
    - Pantry: current state (no date filtering)
    """
    if start is None or end is None:
        start, end = _default_range()

    start_dt = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(end, datetime.max.time())

    # --- Full detail tables (parallel-safe, no dependencies) ---

    # Defusion logs
    defusion_q = await db.execute(
        select(DefusionLog)
        .where(DefusionLog.timestamp >= start_dt, DefusionLog.timestamp <= end_dt)
        .order_by(DefusionLog.timestamp.asc())
    )
    defusion_rows = defusion_q.scalars().all()

    # Check-ins
    checkin_q = await db.execute(
        select(CheckIn)
        .where(CheckIn.timestamp >= start_dt, CheckIn.timestamp <= end_dt)
        .order_by(CheckIn.timestamp.asc())
    )
    checkin_rows = checkin_q.scalars().all()

    # Spending
    spending_q = await db.execute(
        select(Spending)
        .where(Spending.timestamp >= start_dt, Spending.timestamp <= end_dt)
        .order_by(Spending.timestamp.asc())
    )
    spending_rows = spending_q.scalars().all()

    # Apple Health
    health_q = await db.execute(
        select(AppleHealth)
        .where(AppleHealth.date >= start, AppleHealth.date <= end)
        .order_by(AppleHealth.date.asc())
    )
    health_rows = health_q.scalars().all()

    # --- Food choices with plan item context ---

    food_q = await db.execute(
        select(FoodChoice, PlanItem.label, PlanItem.completed_at, DailyPlan.date)
        .join(PlanItem, FoodChoice.plan_item_id == PlanItem.id)
        .join(DailyPlan, PlanItem.plan_id == DailyPlan.id)
        .where(DailyPlan.date >= start, DailyPlan.date <= end)
        .order_by(DailyPlan.date.asc(), PlanItem.order.asc())
    )
    food_rows = food_q.all()

    # --- Plan completion summary by day and category ---

    summary_q = await db.execute(
        select(
            DailyPlan.date,
            DailyPlan.day_type,
            PlanItem.category,
            func.count().label("total"),
            func.sum(case((PlanItem.status == "done", 1), else_=0)).label("done"),
            func.sum(case((PlanItem.status == "skipped", 1), else_=0)).label("skipped"),
            func.sum(case((PlanItem.status == "pending", 1), else_=0)).label("pending"),
        )
        .join(PlanItem, DailyPlan.id == PlanItem.plan_id)
        .where(DailyPlan.date >= start, DailyPlan.date <= end)
        .group_by(DailyPlan.date, DailyPlan.day_type, PlanItem.category)
        .order_by(DailyPlan.date.asc(), PlanItem.category.asc())
    )
    summary_rows = summary_q.all()

    # --- Pantry (current state, no date filter) ---

    pantry_q = await db.execute(
        select(Pantry).order_by(Pantry.category.asc(), Pantry.name.asc())
    )
    pantry_rows = pantry_q.scalars().all()

    # --- Build response ---

    return {
        "range": {"start": start.isoformat(), "end": end.isoformat()},
        "defusion_logs": [
            {
                "timestamp": r.timestamp.isoformat(),
                "trigger_type": r.trigger_type,
                "intensity": r.intensity,
                "outcome": r.outcome,
                "duration_seconds": r.duration_seconds,
            }
            for r in defusion_rows
        ],
        "check_ins": [
            {
                "timestamp": r.timestamp.isoformat(),
                "energy": r.energy,
                "mood": r.mood,
            }
            for r in checkin_rows
        ],
        "spending": [
            {
                "timestamp": r.timestamp.isoformat(),
                "amount": r.amount,
                "category": r.category,
            }
            for r in spending_rows
        ],
        "health": [
            {
                "date": r.date.isoformat(),
                "metric": r.metric,
                "value": r.value,
            }
            for r in health_rows
        ],
        "food_choices": [
            {
                "date": row.date.isoformat(),
                "meal_label": row.label,
                "choice_type": row.FoodChoice.choice_type,
                "selected": row.FoodChoice.selected,
                "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            }
            for row in food_rows
        ],
        "daily_completion": [
            {
                "date": row.date.isoformat(),
                "day_type": row.day_type,
                "category": row.category,
                "total": row.total,
                "done": row.done,
                "skipped": row.skipped,
                "pending": row.pending,
            }
            for row in summary_rows
        ],
        "pantry": [
            {
                "name": r.name,
                "category": r.category,
                "currently_stocked": r.currently_stocked,
            }
            for r in pantry_rows
        ],
    }
