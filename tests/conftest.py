import os
import bcrypt
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

# Force SQLite and set test auth tokens before importing app
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test.db"
os.environ["API_TOKEN"] = "test-token-for-testing"
os.environ["SESSION_SECRET"] = "test-session-secret"
os.environ["APP_USERNAME"] = "testuser"
os.environ["APP_PASSWORD_HASH"] = bcrypt.hashpw(b"testpass", bcrypt.gensalt(rounds=4)).decode()

from app.database import Base, get_db
from app.main import app

test_engine = create_async_engine("sqlite+aiosqlite:///./test.db", echo=False)
TestSession = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db():
    async with TestSession() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        # Disable FK checks for clean drop with circular FKs (SQLite)
        await conn.exec_driver_sql("PRAGMA foreign_keys = OFF")
        await conn.run_sync(Base.metadata.drop_all)
        await conn.exec_driver_sql("PRAGMA foreign_keys = ON")


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
