from datetime import datetime, date
from zoneinfo import ZoneInfo
from sqlalchemy import Integer, Float, String, DateTime, Date, Boolean, JSON, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
import enum

PACIFIC = ZoneInfo("America/Los_Angeles")


def now_pacific() -> datetime:
    """Return current time in Pacific, as a naive datetime (no tzinfo).

    All DateTime columns in this project use TIMESTAMP WITHOUT TIME ZONE.
    asyncpg rejects tz-aware datetimes for these columns, so we must strip tzinfo.
    """
    return datetime.now(PACIFIC).replace(tzinfo=None)


class SpendingCategory(str, enum.Enum):
    GROCERIES = "Groceries"
    SUBSCRIPTIONS = "Subscriptions"
    ENTERTAINMENT = "Entertainment"
    DINING_OUT = "Dining Out"
    SHOPPING = "Shopping"


class TriggerType(str, enum.Enum):
    SMELL = "Smell"
    SIGHT = "Sight"
    WALK_BY = "Walk-by"
    THOUGHT = "Thought"


class DefusionOutcome(str, enum.Enum):
    STAYED = "stayed"
    DIDNT = "didnt"


class Spending(Base):
    __tablename__ = "spending"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=now_pacific)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)


class DefusionLog(Base):
    __tablename__ = "defusion_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=now_pacific)
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False)
    intensity: Mapped[int] = mapped_column(Integer, nullable=False)
    outcome: Mapped[str] = mapped_column(String(10), nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=10)


class CheckIn(Base):
    __tablename__ = "check_ins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=now_pacific)
    energy: Mapped[int] = mapped_column(Integer, nullable=False)
    mood: Mapped[int] = mapped_column(Integer, nullable=False)


class AppleHealth(Base):
    __tablename__ = "apple_health"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    metric: Mapped[str] = mapped_column(String(50), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)


# --- Runsheet Models ---


class PlanStatus(str, enum.Enum):
    ACTIVE = "active"
    COMPLETED = "completed"


class ItemStatus(str, enum.Enum):
    PENDING = "pending"
    DONE = "done"
    SKIPPED = "skipped"


class ItemCategory(str, enum.Enum):
    GYM = "gym"
    WALK = "walk"
    MEAL = "meal"
    PREP = "prep"
    CLEANING = "cleaning"
    NSDR = "nsdr"
    BRAIN_BUILDING = "brain-building"
    CUSTOM = "custom"
    COFFEE = "coffee"
    SHOPPING = "shopping"
    SHOWER = "shower"
    LAUNDRY = "laundry"


class ChoiceType(str, enum.Enum):
    OATMEAL_FRUIT = "oatmeal_fruit"
    VEGGIE_BOWL_VEG = "veggie_bowl_veg"
    SNACK_VEG = "snack_veg"
    SNACK_FRUIT = "snack_fruit"
    PREWORKOUT_FRUIT = "preworkout_fruit"


class DailyPlan(Base):
    __tablename__ = "daily_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, unique=True)
    day_type: Mapped[str] = mapped_column(String(50), nullable=False)
    week_number: Mapped[int] = mapped_column(Integer, nullable=False)
    custom_edits: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=PlanStatus.ACTIVE.value)

    items: Mapped[list["PlanItem"]] = relationship("PlanItem", back_populates="plan", cascade="all, delete-orphan", order_by="PlanItem.order")


class PlanItem(Base):
    __tablename__ = "plan_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("daily_plans.id"), nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=ItemStatus.PENDING.value)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    food_choice_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("food_choices.id", use_alter=True, name="fk_plan_items_food_choice_id"), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    plan: Mapped["DailyPlan"] = relationship("DailyPlan", back_populates="items")
    food_choice: Mapped["FoodChoice | None"] = relationship("FoodChoice", back_populates="plan_item", foreign_keys="FoodChoice.plan_item_id")


class FoodChoice(Base):
    __tablename__ = "food_choices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_item_id: Mapped[int] = mapped_column(Integer, ForeignKey("plan_items.id"), nullable=False)
    choice_type: Mapped[str] = mapped_column(String(30), nullable=False)
    selected: Mapped[str | None] = mapped_column(String(200), nullable=True)
    options: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    plan_item: Mapped["PlanItem"] = relationship("PlanItem", back_populates="food_choice", foreign_keys=[plan_item_id])


class Pantry(Base):
    __tablename__ = "pantry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    category: Mapped[str] = mapped_column(String(20), nullable=False)  # fruit or vegetable
    currently_stocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_updated: Mapped[datetime] = mapped_column(DateTime, default=now_pacific)
