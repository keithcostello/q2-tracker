"""Tests for the Pantry API endpoints."""

import pytest

AUTH = {"Authorization": "Bearer test-token-for-testing"}


# --- Auth Tests ---

@pytest.mark.asyncio
async def test_unauth_get_pantry(client):
    resp = await client.get("/api/pantry")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_unauth_put_pantry(client):
    resp = await client.put("/api/pantry", json={"items": []})
    assert resp.status_code == 401


# --- Pantry CRUD Tests ---

@pytest.mark.asyncio
async def test_get_empty_pantry(client):
    """Empty pantry should return empty list."""
    resp = await client.get("/api/pantry", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_bulk_update_creates_items(client):
    """PUT /pantry should create new items if they don't exist."""
    resp = await client.put("/api/pantry", json={
        "items": [
            {"name": "apples", "category": "fruit", "currently_stocked": True},
            {"name": "carrots", "category": "vegetable", "currently_stocked": True},
            {"name": "bananas", "category": "fruit", "currently_stocked": False},
        ]
    }, headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 3
    assert "apples" in data["updated"]


@pytest.mark.asyncio
async def test_bulk_update_then_list(client):
    """After bulk update, GET should return all items."""
    await client.put("/api/pantry", json={
        "items": [
            {"name": "apples", "category": "fruit", "currently_stocked": True},
            {"name": "spinach", "category": "vegetable", "currently_stocked": True},
        ]
    }, headers=AUTH)

    resp = await client.get("/api/pantry", headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    names = {d["name"] for d in data}
    assert "apples" in names
    assert "spinach" in names


@pytest.mark.asyncio
async def test_update_existing_item(client):
    """PUT should update existing items, not duplicate them."""
    await client.put("/api/pantry", json={
        "items": [{"name": "apples", "category": "fruit", "currently_stocked": True}]
    }, headers=AUTH)

    # Update stocked status
    await client.put("/api/pantry", json={
        "items": [{"name": "apples", "currently_stocked": False}]
    }, headers=AUTH)

    resp = await client.get("/api/pantry", headers=AUTH)
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "apples"
    assert data[0]["currently_stocked"] is False


@pytest.mark.asyncio
async def test_filter_by_category(client):
    """GET with category filter should only return matching items."""
    await client.put("/api/pantry", json={
        "items": [
            {"name": "apples", "category": "fruit", "currently_stocked": True},
            {"name": "carrots", "category": "vegetable", "currently_stocked": True},
        ]
    }, headers=AUTH)

    resp = await client.get("/api/pantry?category=fruit", headers=AUTH)
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "apples"


@pytest.mark.asyncio
async def test_filter_stocked_only(client):
    """GET with stocked_only=true should only return stocked items."""
    await client.put("/api/pantry", json={
        "items": [
            {"name": "apples", "category": "fruit", "currently_stocked": True},
            {"name": "bananas", "category": "fruit", "currently_stocked": False},
        ]
    }, headers=AUTH)

    resp = await client.get("/api/pantry?stocked_only=true", headers=AUTH)
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "apples"


@pytest.mark.asyncio
async def test_pantry_items_sorted(client):
    """Items should be sorted by category then name."""
    await client.put("/api/pantry", json={
        "items": [
            {"name": "zucchini", "category": "vegetable", "currently_stocked": True},
            {"name": "apples", "category": "fruit", "currently_stocked": True},
            {"name": "carrots", "category": "vegetable", "currently_stocked": True},
        ]
    }, headers=AUTH)

    resp = await client.get("/api/pantry", headers=AUTH)
    data = resp.json()
    names = [d["name"] for d in data]
    # fruit before vegetable, then alphabetical within
    assert names[0] == "apples"


@pytest.mark.asyncio
async def test_bulk_update_skips_empty_name(client):
    """Items with empty/missing name should be skipped."""
    resp = await client.put("/api/pantry", json={
        "items": [
            {"name": "apples", "category": "fruit", "currently_stocked": True},
            {"name": "", "category": "fruit", "currently_stocked": True},
            {"category": "fruit", "currently_stocked": True},
        ]
    }, headers=AUTH)
    data = resp.json()
    assert data["count"] == 1


@pytest.mark.asyncio
async def test_pantry_item_has_all_fields(client):
    """Each pantry item should have all required fields."""
    await client.put("/api/pantry", json={
        "items": [{"name": "apples", "category": "fruit", "currently_stocked": True}]
    }, headers=AUTH)

    resp = await client.get("/api/pantry", headers=AUTH)
    item = resp.json()[0]
    assert "id" in item
    assert "name" in item
    assert "category" in item
    assert "currently_stocked" in item
    assert "last_updated" in item
