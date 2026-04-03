import pytest
from datetime import datetime, date

AUTH = {"Authorization": "Bearer test-token-for-testing"}


# --- Spending Tests ---

@pytest.mark.asyncio
async def test_post_spending(client):
    resp = await client.post("/api/spending", json={
        "amount": 42.50,
        "category": "Groceries"
    }, headers=AUTH)
    assert resp.status_code == 201
    data = resp.json()
    assert data["amount"] == 42.50
    assert data["category"] == "Groceries"
    assert "id" in data
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_post_spending_invalid_category(client):
    resp = await client.post("/api/spending", json={
        "amount": 10.00,
        "category": "InvalidCat"
    }, headers=AUTH)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_spending(client):
    await client.post("/api/spending", json={"amount": 10.00, "category": "Groceries"}, headers=AUTH)
    await client.post("/api/spending", json={"amount": 20.00, "category": "Dining Out"}, headers=AUTH)

    resp = await client.get("/api/spending", headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


@pytest.mark.asyncio
async def test_get_spending_filter_category(client):
    await client.post("/api/spending", json={"amount": 10.00, "category": "Groceries"}, headers=AUTH)
    await client.post("/api/spending", json={"amount": 20.00, "category": "Dining Out"}, headers=AUTH)

    resp = await client.get("/api/spending?category=Groceries", headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["category"] == "Groceries"


@pytest.mark.asyncio
async def test_spending_summary(client):
    await client.post("/api/spending", json={"amount": 10.00, "category": "Groceries"}, headers=AUTH)
    await client.post("/api/spending", json={"amount": 25.00, "category": "Groceries"}, headers=AUTH)
    await client.post("/api/spending", json={"amount": 15.00, "category": "Dining Out"}, headers=AUTH)

    resp = await client.get("/api/spending/summary", headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    # Should have two categories
    categories = {item["category"]: item["total"] for item in data}
    assert categories["Groceries"] == 35.00
    assert categories["Dining Out"] == 15.00


# --- Defusion Tests ---

@pytest.mark.asyncio
async def test_post_defusion(client):
    resp = await client.post("/api/defusion", json={
        "trigger_type": "Smell",
        "intensity": 4,
        "outcome": "stayed"
    }, headers=AUTH)
    assert resp.status_code == 201
    data = resp.json()
    assert data["trigger_type"] == "Smell"
    assert data["intensity"] == 4
    assert data["outcome"] == "stayed"
    assert data["duration_seconds"] == 120


@pytest.mark.asyncio
async def test_post_defusion_custom_duration(client):
    resp = await client.post("/api/defusion", json={
        "trigger_type": "Sight",
        "intensity": 3,
        "outcome": "didnt",
        "duration_seconds": 60
    }, headers=AUTH)
    assert resp.status_code == 201
    assert resp.json()["duration_seconds"] == 60


@pytest.mark.asyncio
async def test_post_defusion_invalid_trigger(client):
    resp = await client.post("/api/defusion", json={
        "trigger_type": "BadTrigger",
        "intensity": 3,
        "outcome": "stayed"
    }, headers=AUTH)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_defusion_success_rate(client):
    await client.post("/api/defusion", json={"trigger_type": "Smell", "intensity": 3, "outcome": "stayed"}, headers=AUTH)
    await client.post("/api/defusion", json={"trigger_type": "Smell", "intensity": 4, "outcome": "stayed"}, headers=AUTH)
    await client.post("/api/defusion", json={"trigger_type": "Smell", "intensity": 5, "outcome": "didnt"}, headers=AUTH)
    await client.post("/api/defusion", json={"trigger_type": "Sight", "intensity": 2, "outcome": "stayed"}, headers=AUTH)

    resp = await client.get("/api/defusion/success-rate", headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    rates = {item["trigger_type"]: item for item in data}
    assert rates["Smell"]["total"] == 3
    assert rates["Smell"]["stayed"] == 2
    assert abs(rates["Smell"]["rate"] - 66.67) < 1
    assert rates["Sight"]["rate"] == 100.0


@pytest.mark.asyncio
async def test_get_defusion(client):
    await client.post("/api/defusion", json={"trigger_type": "Smell", "intensity": 3, "outcome": "stayed"}, headers=AUTH)
    resp = await client.get("/api/defusion", headers=AUTH)
    assert resp.status_code == 200
    assert len(resp.json()) == 1


# --- Check-In Tests ---

@pytest.mark.asyncio
async def test_post_checkin(client):
    resp = await client.post("/api/checkin", json={
        "energy": 4,
        "mood": 3
    }, headers=AUTH)
    assert resp.status_code == 201
    data = resp.json()
    assert data["energy"] == 4
    assert data["mood"] == 3


@pytest.mark.asyncio
async def test_post_checkin_invalid_range(client):
    resp = await client.post("/api/checkin", json={
        "energy": 6,
        "mood": 3
    }, headers=AUTH)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_checkins(client):
    await client.post("/api/checkin", json={"energy": 4, "mood": 3}, headers=AUTH)
    await client.post("/api/checkin", json={"energy": 2, "mood": 5}, headers=AUTH)

    resp = await client.get("/api/checkins", headers=AUTH)
    assert resp.status_code == 200
    assert len(resp.json()) == 2


# --- Health Tests ---

@pytest.mark.asyncio
async def test_post_health(client):
    resp = await client.post("/api/health", json={
        "date": "2026-04-01",
        "metric": "steps",
        "value": 8500
    }, headers=AUTH)
    assert resp.status_code == 201
    data = resp.json()
    assert data["metric"] == "steps"
    assert data["value"] == 8500


@pytest.mark.asyncio
async def test_health_trend(client):
    await client.post("/api/health", json={"date": "2026-04-01", "metric": "steps", "value": 8000}, headers=AUTH)
    await client.post("/api/health", json={"date": "2026-04-02", "metric": "steps", "value": 9000}, headers=AUTH)
    await client.post("/api/health", json={"date": "2026-04-01", "metric": "sleep_hours", "value": 7.5}, headers=AUTH)

    resp = await client.get("/api/health/trend?metric=steps", headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert all(d["metric"] == "steps" for d in data)


@pytest.mark.asyncio
async def test_health_summary(client):
    await client.post("/api/health", json={"date": "2026-04-01", "metric": "steps", "value": 8000}, headers=AUTH)
    await client.post("/api/health", json={"date": "2026-04-01", "metric": "sleep_hours", "value": 7.5}, headers=AUTH)
    await client.post("/api/health", json={"date": "2026-04-02", "metric": "steps", "value": 9000}, headers=AUTH)

    resp = await client.get("/api/health/summary?date=2026-04-01", headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    metrics = {d["metric"]: d["value"] for d in data}
    assert metrics["steps"] == 8000
    assert metrics["sleep_hours"] == 7.5


# --- Status Tests ---

@pytest.mark.asyncio
async def test_status(client):
    resp = await client.get("/api/status")
    assert resp.status_code == 200
    data = resp.json()
    a