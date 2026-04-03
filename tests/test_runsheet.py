"""Tests for the Daily Runsheet API endpoints."""

import pytest
from datetime import date, datetime
from unittest.mock import patch

AUTH = {"Authorization": "Bearer test-token-for-testing"}


# --- Auth Tests ---

@pytest.mark.asyncio
async def test_unauth_get_today(client):
    resp = await client.get("/api/runsheet/today")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_unauth_complete_item(client):
    resp = await client.post("/api/runsheet/item/1/complete")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_unauth_skip_item(client):
    resp = await client.post("/api/runsheet/item/1/skip")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_unauth_edit_plan(client):
    resp = await client.post("/api/runsheet/edit", json=[])
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_unauth_food_choice(client):
    resp = await client.post("/api/runsheet/food-choice", json={
        "plan_item_id": 1, "choice_type": "oatmeal_fruit", "selected": "banana"
    })
    assert resp.status_code == 401


# --- Plan Auto-Generation Tests ---

@pytest.mark.asyncio
async def test_get_today_auto_generates_plan(client):
    """GET /today should auto-generate a plan if none exists."""
    resp = await client.get("/api/runsheet/today", headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert data["date"] == date.today().isoformat()
    assert data["status"] == "active"
    assert len(data["items"]) > 0


@pytest.mark.asyncio
async def test_get_today_returns_existing_plan(client):
    """Second call should return the same plan, not create a new one."""
    resp1 = await client.get("/api/runsheet/today", headers=AUTH)
    resp2 = await client.get("/api/runsheet/today", headers=AUTH)
    assert resp1.json()["id"] == resp2.json()["id"]


@pytest.mark.asyncio
async def test_plan_has_correct_day_type(client):
    """Plan day_type should match the schedule config for today."""
    resp = await client.get("/api/runsheet/today", headers=AUTH)
    data = resp.json()
    assert data["day_type"] != ""
    assert data["week_number"] in [1, 2]


@pytest.mark.asyncio
async def test_plan_items_have_correct_fields(client):
    """Each item should have all required fields."""
    resp = await client.get("/api/runsheet/today", headers=AUTH)
    data = resp.json()
    for item in data["items"]:
        assert "id" in item
        assert "order" in item
        assert "label" in item
        assert "status" in item
        assert item["status"] == "pending"
        assert "category" in item


@pytest.mark.asyncio
async def test_plan_items_ordered_sequentially(client):
    """Items should have sequential order values."""
    resp = await client.get("/api/runsheet/today", headers=AUTH)
    items = resp.json()["items"]
    orders = [i["order"] for i in items]
    assert orders == sorted(orders)
    assert orders[0] == 1


# --- Item Complete/Skip Tests ---

@pytest.mark.asyncio
async def test_complete_item(client):
    """Completing an item sets status to done and records completed_at."""
    # Get plan to have items
    resp = await client.get("/api/runsheet/today", headers=AUTH)
    item_id = resp.json()["items"][0]["id"]

    resp = await client.post(f"/api/runsheet/item/{item_id}/complete", headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "done"
    assert data["completed_at"] is not None


@pytest.mark.asyncio
async def test_complete_nonexistent_item(client):
    resp = await client.post("/api/runsheet/item/9999/complete", headers=AUTH)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_skip_item(client):
    """Skipping an item sets status to skipped."""
    resp = await client.get("/api/runsheet/today", headers=AUTH)
    item_id = resp.json()["items"][0]["id"]

    resp = await client.post(f"/api/runsheet/item/{item_id}/skip", headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "skipped"


@pytest.mark.asyncio
async def test_skip_nonexistent_item(client):
    resp = await client.post("/api/runsheet/item/9999/skip", headers=AUTH)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_complete_then_verify_in_plan(client):
    """After completing an item, GET /today should show it as done."""
    resp = await client.get("/api/runsheet/today", headers=AUTH)
    item_id = resp.json()["items"][0]["id"]

    await client.post(f"/api/runsheet/item/{item_id}/complete", headers=AUTH)

    resp = await client.get("/api/runsheet/today", headers=AUTH)
    items_by_id = {i["id"]: i for i in resp.json()["items"]}
    assert items_by_id[item_id]["status"] == "done"


# --- Edit Plan Tests ---

@pytest.mark.asyncio
async def test_edit_add_item(client):
    """Adding an item via edit endpoint."""
    # Ensure plan exists
    await client.get("/api/runsheet/today", headers=AUTH)

    resp = await client.post("/api/runsheet/edit", json=[
        {"action": "add", "label": "Extra task", "category": "custom"}
    ], headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert data["edits"][0]["action"] == "added"
    assert "item_id" in data["edits"][0]


@pytest.mark.asyncio
async def test_edit_delete_item(client):
    """Deleting an item via edit endpoint."""
    resp = await client.get("/api/runsheet/today", headers=AUTH)
    item_id = resp.json()["items"][-1]["id"]

    resp = await client.post("/api/runsheet/edit", json=[
        {"action": "delete", "item_id": item_id}
    ], headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["edits"][0]["action"] == "deleted"


@pytest.mark.asyncio
async def test_edit_reorder_items(client):
    """Reordering items via edit endpoint."""
    resp = await client.get("/api/runsheet/today", headers=AUTH)
    items = resp.json()["items"]
    item_ids = [i["id"] for i in items]
    reversed_ids = list(reversed(item_ids))

    resp = await client.post("/api/runsheet/edit", json=[
        {"action": "reorder", "new_order": reversed_ids}
    ], headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["edits"][0]["action"] == "reordered"


@pytest.mark.asyncio
async def test_edit_unknown_action(client):
    """Unknown edit action should return 422."""
    await client.get("/api/runsheet/today", headers=AUTH)

    resp = await client.post("/api/runsheet/edit", json=[
        {"action": "foobar"}
    ], headers=AUTH)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_edit_add_missing_label(client):
    """Add without label should return 422."""
    await client.get("/api/runsheet/today", headers=AUTH)

    resp = await client.post("/api/runsheet/edit", json=[
        {"action": "add", "category": "custom"}
    ], headers=AUTH)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_edit_no_plan_returns_404(client):
    """Edit with no plan for today should return 404."""
    # Use a mocked date that won't have a plan
    # Actually we just don't create one first - but the conftest drops all tables
    # So if we don't call /today first, there's no plan
    resp = await client.post("/api/runsheet/edit", json=[
        {"action": "add", "label": "Test", "category": "custom"}
    ], headers=AUTH)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_edit_delete_nonexistent_item(client):
    """Deleting a nonexistent item should 404."""
    await client.get("/api/runsheet/today", headers=AUTH)

    resp = await client.post("/api/runsheet/edit", json=[
        {"action": "delete", "item_id": 99999}
    ], headers=AUTH)
    assert resp.status_code == 404


# --- Food Choice Tests ---

@pytest.mark.asyncio
async def test_record_food_choice(client):
    """Recording a food choice for a plan item."""
    resp = await client.get("/api/runsheet/today", headers=AUTH)
    # Find a meal item
    meal_item = next(
        (i for i in resp.json()["items"] if i["category"] == "meal"),
        resp.json()["items"][0],
    )

    resp = await client.post("/api/runsheet/food-choice", json={
        "plan_item_id": meal_item["id"],
        "choice_type": "oatmeal_fruit",
        "selected": "banana",
        "options": {"available": ["banana", "apple", "blueberry"]},
    }, headers=AUTH)
    assert resp.status_code == 201
    data = resp.json()
    assert data["selected"] == "banana"
    assert data["choice_type"] == "oatmeal_fruit"
    assert data["plan_item_id"] == meal_item["id"]


@pytest.mark.asyncio
async def test_food_choice_invalid_type(client):
    """Invalid choice_type should return 422."""
    resp = await client.get("/api/runsheet/today", headers=AUTH)
    item_id = resp.json()["items"][0]["id"]

    resp = await client.post("/api/runsheet/food-choice", json={
        "plan_item_id": item_id,
        "choice_type": "invalid_type",
        "selected": "banana",
    }, headers=AUTH)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_food_choice_nonexistent_item(client):
    """Food choice for nonexistent item should 404."""
    resp = await client.post("/api/runsheet/food-choice", json={
        "plan_item_id": 99999,
        "choice_type": "oatmeal_fruit",
        "selected": "banana",
    }, headers=AUTH)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_food_choice_shows_in_plan(client):
    """After recording a food choice, it should appear in GET /today."""
    resp = await client.get("/api/runsheet/today", headers=AUTH)
    meal_item = next(
        (i for i in resp.json()["items"] if i["category"] == "meal"),
        resp.json()["items"][0],
    )

    await client.post("/api/runsheet/food-choice", json={
        "plan_item_id": meal_item["id"],
        "choice_type": "oatmeal_fruit",
        "selected": "strawberry",
    }, headers=AUTH)

    resp = await client.get("/api/runsheet/today", headers=AUTH)
    items_by_id = {i["id"]: i for i in resp.json()["items"]}
    assert items_by_id[meal_item["id"]]["food_choice"] is not None
    assert items_by_id[meal_item["id"]]["food_choice"]["selected"] == "strawberry"


# --- Schedule Config Tests ---

def test_get_week_number():
    """Week number should be 1 or 2."""
    from app.routers.runsheet import get_week_number
    d = date(2026, 4, 3)
    wn = get_week_number(d)
    assert wn in [1, 2]


def test_get_day_type():
    """Day type should match schedule for the weekday."""
    from app.routers.runsheet import get_day_type
    # April 3 2026 is a Friday
    dt = get_day_type(date(2026, 4, 3))
    assert "Friday" in dt


def test_get_day_type_monday():
    """Monday should include HIIT in the title."""
    from app.routers.runsheet import get_day_type
    # April 6 2026 is a Monday
    dt = get_day_type(date(2026, 4, 6))
    assert "Monday" in dt
    assert "HIIT" in dt


def test_week_number_anchored_to_start_date():
    """Week number should be anchored to system start date (2026-03-16), not ISO weeks."""
    from app.routers.runsheet import get_week_number, SYSTEM_START_DATE
    assert SYSTEM_START_DATE == date(2026, 3, 16)
    # Mar 16-22 = Week 1
    assert get_week_number(date(2026, 3, 16)) == 1
    assert get_week_number(date(2026, 3, 22)) == 1
    # Mar 23-29 = Week 2
    assert get_week_number(date(2026, 3, 23)) == 2
    assert get_week_number(date(2026, 3, 29)) == 2
    # Mar 30 - Apr 5 = Week 1
    assert get_week_number(date(2026, 3, 30)) == 1
    assert get_week_number(date(2026, 4, 3)) == 1
    # Apr 6-12 = Week 2
    assert get_week_number(date(2026, 4, 6)) == 2


def test_get_day_items_returns_full_schedule():
    """Day items from JSON should have 20+ items (not the old abbreviated 8-10)."""
    from app.routers.runsheet import get_day_items
    # Monday should have 25 items per the config
    items = get_day_items(date(2026, 4, 6))  # Monday
    assert len(items) >= 20
    # Each item has required keys
    for item in items:
        assert "order" in item
        assert "label" in item
        assert "category" in item
