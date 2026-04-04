import pytest

TEST_TOKEN = "test-token-for-testing"
TEST_USERNAME = "testuser"
TEST_PASSWORD = "testpass"


# --- Unauthenticated API requests return 401 ---

@pytest.mark.asyncio
async def test_unauth_post_spending(client):
    resp = await client.post("/api/spending", json={"amount": 10.00, "category": "Groceries"})
    assert resp.status_code == 401

@pytest.mark.asyncio
async def test_unauth_get_spending(client):
    resp = await client.get("/api/spending")
    assert resp.status_code == 401

@pytest.mark.asyncio
async def test_unauth_get_spending_summary(client):
    resp = await client.get("/api/spending/summary")
    assert resp.status_code == 401

@pytest.mark.asyncio
async def test_unauth_post_defusion(client):
    resp = await client.post("/api/defusion", json={"trigger_type": "Smell", "intensity": 3, "outcome": "stayed"})
    assert resp.status_code == 401

@pytest.mark.asyncio
async def test_unauth_get_defusion(client):
    resp = await client.get("/api/defusion")
    assert resp.status_code == 401

@pytest.mark.asyncio
async def test_unauth_get_defusion_success_rate(client):
    resp = await client.get("/api/defusion/success-rate")
    assert resp.status_code == 401

@pytest.mark.asyncio
async def test_unauth_post_checkin(client):
    resp = await client.post("/api/checkin", json={"energy": 4, "mood": 3})
    assert resp.status_code == 401

@pytest.mark.asyncio
async def test_unauth_get_checkins(client):
    resp = await client.get("/api/checkins")
    assert resp.status_code == 401

@pytest.mark.asyncio
async def test_unauth_post_health(client):
    resp = await client.post("/api/health", json={"date": "2026-04-01", "metric": "steps", "value": 8000})
    assert resp.status_code == 401

@pytest.mark.asyncio
async def test_unauth_get_health_trend(client):
    resp = await client.get("/api/health/trend?metric=steps")
    assert resp.status_code == 401

@pytest.mark.asyncio
async def test_unauth_get_health_summary(client):
    resp = await client.get("/api/health/summary?date=2026-04-01")
    assert resp.status_code == 401


# --- Status endpoint remains public ---

@pytest.mark.asyncio
async def test_status_is_public(client):
    resp = await client.get("/api/status")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# --- Wrong Bearer token returns 401 ---

@pytest.mark.asyncio
async def test_wrong_token_post_spending(client):
    resp = await client.post(
        "/api/spending",
        json={"amount": 10.00, "category": "Groceries"},
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert resp.status_code == 401

@pytest.mark.asyncio
async def test_wrong_token_get_spending(client):
    resp = await client.get(
        "/api/spending",
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert resp.status_code == 401


# --- Authenticated API requests pass through ---

@pytest.mark.asyncio
async def test_auth_post_spending(client):
    resp = await client.post(
        "/api/spending",
        json={"amount": 42.50, "category": "Groceries"},
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
    )
    assert resp.status_code == 201
    assert resp.json()["amount"] == 42.50

@pytest.mark.asyncio
async def test_auth_get_spending(client):
    resp = await client.get(
        "/api/spending",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
    )
    assert resp.status_code == 200

@pytest.mark.asyncio
async def test_auth_post_defusion(client):
    resp = await client.post(
        "/api/defusion",
        json={"trigger_type": "Smell", "intensity": 3, "outcome": "stayed"},
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
    )
    assert resp.status_code == 201

@pytest.mark.asyncio
async def test_auth_get_defusion(client):
    resp = await client.get(
        "/api/defusion",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
    )
    assert resp.status_code == 200

@pytest.mark.asyncio
async def test_auth_post_checkin(client):
    resp = await client.post(
        "/api/checkin",
        json={"energy": 4, "mood": 3},
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
    )
    assert resp.status_code == 201

@pytest.mark.asyncio
async def test_auth_get_checkins(client):
    resp = await client.get(
        "/api/checkins",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
    )
    assert resp.status_code == 200

@pytest.mark.asyncio
async def test_auth_post_health(client):
    resp = await client.post(
        "/api/health",
        json={"date": "2026-04-01", "metric": "steps", "value": 8000},
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
    )
    assert resp.status_code == 201

@pytest.mark.asyncio
async def test_auth_get_health_trend(client):
    resp = await client.get(
        "/api/health/trend?metric=steps",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
    )
    assert resp.status_code == 200

@pytest.mark.asyncio
async def test_auth_get_health_summary(client):
    resp = await client.get(
        "/api/health/summary?date=2026-04-01",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
    )
    assert resp.status_code == 200


# --- Page routes require session ---

@pytest.mark.asyncio
async def test_unauth_tracker_redirects_to_login(client):
    resp = await client.get("/", follow_redirects=False)
    assert resp.status_code == 303
    assert "/login" in resp.headers["location"]

@pytest.mark.asyncio
async def test_unauth_dashboard_redirects_to_login(client):
    resp = await client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 303
    assert "/login" in resp.headers["location"]

@pytest.mark.asyncio
async def test_login_page_loads(client):
    resp = await client.get("/login")
    assert resp.status_code == 200


# --- Login flow ---

@pytest.mark.asyncio
async def test_login_with_correct_credentials(client):
    resp = await client.post(
        "/login",
        data={"username": TEST_USERNAME, "password": TEST_PASSWORD},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"
    assert "session" in resp.cookies or any("session" in c for c in resp.headers.get_list("set-cookie"))

@pytest.mark.asyncio
async def test_login_with_wrong_password(client):
    resp = await client.post(
        "/login",
        data={"username": TEST_USERNAME, "password": "wrong-password"},
        follow_redirects=False,
    )
    assert resp.status_code == 200

@pytest.mark.asyncio
async def test_login_with_wrong_username(client):
    resp = await client.post(
        "/login",
        data={"username": "notauser", "password": TEST_PASSWORD},
        follow_redirects=False,
    )
    assert resp.status_code == 200

@pytest.mark.asyncio
async def test_authenticated_session_accesses_tracker(client):
    login_resp = await client.post(
        "/login",
        data={"username": TEST_USERNAME, "password": TEST_PASSWORD},
        follow_redirects=False,
    )
    cookies = login_resp.cookies
    resp = await client.get("/", cookies=cookies)
    assert resp.status_code == 200

@pytest.mark.asyncio
async def test_authenticated_session_accesses_dashboard(client):
    login_resp = await client.post(
        "/login",
        data={"username": TEST_USERNAME, "password": TEST_PASSWORD},
        follow_redirects=False,
    )
    cookies = login_resp.cookies
    resp = await client.get("/dashboard", cookies=cookies)
    assert resp.status_code == 200
