# Q2 Tracker Backend

Real-time tracker for spending, cognitive defusion protocols, mood/energy check-ins, and Apple Health metrics.

## Tech Stack
- Python 3.11+ / FastAPI / Uvicorn
- PostgreSQL (via SQLAlchemy async)
- Jinja2 templates + Chart.js for dashboard

## Local Development

```bash
pip install -r requirements.txt
export DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/q2tracker"
uvicorn app.main:app --reload
```

## Testing

```bash
pytest tests/ -v
```

## Deploy
Push to Railway. It reads `Procfile` and `railway.toml` automatically.
`DATABASE_URL` is set by Railway's PostgreSQL plugin.
