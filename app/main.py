import os
import logging
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, Query, HTTPException, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, init_db, engine, Base
from app.models import (
    Spending, DefusionLog, CheckIn, AppleHealth,
    SpendingCategory, TriggerType, DefusionOutcome,
)
from app.auth import verify_api_token, require_session, verify_credentials, API_TOKEN

logger = logging.getLogger(__name__)

PACIFIC = ZoneInfo("America/Los_Angeles")

# --- Config ---

SESSION_SECRET = os.environ.get("SESSION_SECRET", "change-me-in-production")


def current_week() -> tuple[date, date]:
    """Return (Monday, Sunday) of the current week."""
    today = datetime.now(PACIFIC).date()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Q2 Tracker", lifespan=lifespan)

app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# Serve the Daily Runsheet PWA at /runsheet — try multiple paths
_runsheet_candidates = [
    os.path.join(PROJECT_DIR, "runsheet"),
    os.path.join(os.getcwd(), "runsheet"),
    "/app/runsheet",
]
_runsheet_mounted = False
for _rpath in _runsheet_candidates:
    if os.path.isdir(_rpath):
        app.mount("/runsheet", StaticFiles(directory=_rpath, html=True), name="runsheet")
        logger.info(f"Mounted /runsheet from {_rpath}")
        _runsheet_mounted = True
        break

if not _runsheet_mounted:
    logger.warning(f"runsheet/ directory not found. Tried: {_runsheet_candidates}")


# --- Pydantic Schemas ---

class SpendingIn(BaseModel):
    amount: float = Field(gt=0)
    category: SpendingCategory

class SpendingOut(BaseModel):
    id: int
    timestamp: datetime
    amount: float
    category: str

class DefusionIn(BaseModel):
    trigger_type: TriggerType
    intensity: int = Field(ge=1, le=5)
    outcome: DefusionOutcome
    duration_seconds: int = 120

class DefusionOut(BaseModel):
    id: int
    timestamp: datetime
    trigger_type: str
    intensity: int
    outcome: str
    duration_seconds: int

class CheckInIn(BaseModel):
    energy: int = Field(ge=1, le=5)
    mood: int = Field(ge=1, le=5)

class CheckInOut(BaseModel):
    id: int
    timestamp: datetime
    energy: int
    mood: int

class HealthIn(BaseModel):
    date: date
    metric: str
    value: float

class HealthOut(BaseModel):
    id: int
    date: date
    metric: str
    value: float


# --- Login Routes ---

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = ""):
    return templates.TemplateResponse("login.html", {"request": request, "error": error})


@app.post("/login")
async def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    if verify_credentials(username, password):
        request.session["authenticated"] = True
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": "Wrong username or password."},
        status_code=200,
    )


# --- Page Routes (session-protected) ---

@app.get("/", response_class=HTMLResponse)
async def tracker_page(request: Request):
    if not require_session(request):
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse("tracker.html", {"request": request, "api_token": API_TOKEN})


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    if not require_session(request):
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse("dashboard.html", {"request": request, "api_token": API_TOKEN})


# --- Spending Endpoints (token-protected) ---

@app.post("/api/spending", response_model=SpendingOut, status_code=201, dependencies=[Depends(verify_api_token)])
async def create_spending(data: SpendingIn, db: AsyncSession = Depends(get_db)):
    entry = Spending(amount=data.amount, category=data.category.value)
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


@app.get("/api/spending", response_model=list[SpendingOut], dependencies=[Depends(verify_api_token)])
async def get_spending(
    start: Optional[date] = None,
    end: Optional[date] = None,
    category: Optional[SpendingCategory] = None,
    db: AsyncSession = Depends(get_db),
):
    if start is None and end is None:
        start, end = current_week()
    q = select(Spending)
    if start:
        q = q.where(Spending.timestamp >= datetime.combine(start, datetime.min.time()))
    if end:
        q = q.where(Spending.timestamp <= datetime.combine(end, datetime.max.time()))
    if category:
        q = q.where(Spending.category == category.value)
    q = q.order_by(Spending.timestamp.desc())
    result = await db.execute(q)
    return result.scalars().all()


@app.get("/api/spending/summary", dependencies=[Depends(verify_api_token)])
async def spending_summary(
    start: Optional[date] = None,
    end: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
):
    if start is None and end is None:
        start, end = current_week()
    q = select(Spending.category, func.sum(Spending.amount).label("total"))
    if start:
        q = q.where(Spending.timestamp >= datetime.combine(start, datetime.min.time()))
    if end:
        q = q.where(Spending.timestamp <= datetime.combine(end, datetime.max.time()))
    q = q.group_by(Spending.category)
    result = await db.execute(q)
    return [{"category": row.category, "total": round(row.total, 2)} for row in result.all()]


# --- Defusion Endpoints (token-protected) ---

@app.post("/api/defusion", response_model=DefusionOut, status_code=201, dependencies=[Depends(verify_api_token)])
async def create_defusion(data: DefusionIn, db: AsyncSession = Depends(get_db)):
    entry = DefusionLog(
        trigger_type=data.trigger_type.value,
        intensity=data.intensity,
        outcome=data.outcome.value,
        duration_seconds=data.duration_seconds,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


@app.get("/api/defusion", response_model=list[DefusionOut], dependencies=[Depends(verify_api_token)])
async def get_defusion(
    start: Optional[date] = None,
    end: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
):
    if start is None and end is None:
        start, end = current_week()
    q = select(DefusionLog)
    if start:
        q = q.where(DefusionLog.timestamp >= datetime.combine(start, datetime.min.time()))
    if end:
        q = q.where(DefusionLog.timestamp <= datetime.combine(end, datetime.max.time()))
    q = q.order_by(DefusionLog.timestamp.desc())
    result = await db.execute(q)
    return result.scalars().all()


@app.get("/api/defusion/success-rate", dependencies=[Depends(verify_api_token)])
async def defusion_success_rate(db: AsyncSession = Depends(get_db)):
    q = select(
        DefusionLog.trigger_type,
        func.count().label("total"),
        func.sum(case((DefusionLog.outcome == "stayed", 1), else_=0)).label("stayed"),
    ).group_by(DefusionLog.trigger_type)
    result = await db.execute(q)
    return [
        {
            "trigger_type": row.trigger_type,
            "total": row.total,
            "stayed": row.stayed,
            "rate": round((row.stayed / row.total) * 100, 2) if row.total > 0 else 0,
        }
        for row in result.all()
    ]


# --- Check-In Endpoints (token-protected) ---

@app.post("/api/checkin", response_model=CheckInOut, status_code=201, dependencies=[Depends(verify_api_token)])
async def create_checkin(data: CheckInIn, db: AsyncSession = Depends(get_db)):
    entry = CheckIn(energy=data.energy, mood=data.mood)
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


@app.get("/api/checkins", response_model=list[CheckInOut], dependencies=[Depends(verify_api_token)])
async def get_checkins(
    start: Optional[date] = None,
    end: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
):
    if start is None and end is None:
        start, end = current_week()
    q = select(CheckIn)
    if start:
        q = q.where(CheckIn.timestamp >= datetime.combine(start, datetime.min.time()))
    if end:
        q = q.where(CheckIn.timestamp <= datetime.combine(end, datetime.max.time()))
    q = q.order_by(CheckIn.timestamp.desc())
    result = await db.execute(q)
    return result.scalars().all()


# --- Health Endpoints (token-protected) ---

@app.post("/api/health", response_model=HealthOut, status_code=201, dependencies=[Depends(verify_api_token)])
async def create_health(data: HealthIn, db: AsyncSession = Depends(get_db)):
    entry = AppleHealth(date=data.date, metric=data.metric, value=data.value)
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


@app.get("/api/health/trend", response_model=list[HealthOut], dependencies=[Depends(verify_api_token)])
async def health_trend(
    metric: str,
    start: Optional[date] = None,
    end: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
):
    if start is None and end is None:
        start, end = current_week()
    q = select(AppleHealth).where(AppleHealth.metric == metric)
    if start:
        q = q.where(AppleHealth.date >= start)
    if end:
        q = q.where(AppleHealth.date <= end)
    q = q.order_by(AppleHealth.date.asc())
    result = await db.execute(q)
    return result.scalars().all()


@app.get("/api/health/summary", response_model=list[HealthOut], dependencies=[Depends(verify_api_token)])
async def health_summary(
    summary_date: Optional[date] = Query(None, alias="date"),
    db: AsyncSession = Depends(get_db),
):
    if summary_date is None:
        summary_date = datetime.now(PACIFIC).date()
    q = select(AppleHealth).where(AppleHealth.date == summary_date)
    result = await db.execute(q)
    return result.scalars().all()


# --- Status Endpoint (public) ---

@app.get("/api/status")
async def status():
    return {"status": "ok"}


# --- Register Routers ---

from app.routers.runsheet import router as runsheet_router
from app.routers.pantry import router as pantry_router

app.include_router(runsheet_router)
app.include_router(pantry_router)
