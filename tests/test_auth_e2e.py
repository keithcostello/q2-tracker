"""End-to-end auth flow integration tests."""

import pytest

TEST_TOKEN = "test-token-for-testing"
TEST_USERNAME = "testuser"
TEST_PASSWORD = "testpass"


# --- Test a: Full login flow then API access ---

@pytest.mark.asyncio
async def test_full_login_then_api_access(client):
    """Login via POST /login, then use Bearer token to hit /api/runsheet/today, verify 200 and plan data returns."""
    # Step 1: POST /login with correct credentials
    login_resp = await client.post(
        "/login",
        data={"username": TEST_USERNAME, "password": TEST_PASSWORD},
        follow_redirects=False,
    )
    assert login_resp.status_code == 303
    assert login_resp.headers["location"] == "/"

    # Step 2: Use Bearer token to access /api/runsheet/today
    api_resp = await client.get(
        "/api/runsheet/today",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
    )
    assert api_resp.status_code == 200
    data = api_resp.json()
    assert "id" in data
    assert "date" in data
    assert "items" in data
    assert isinstance(data["items"], list)


# --- Test b: Session login then page access ---

@pytest.mark.asyncio
async def test_session_login_then_page_access(client):
    """Login via POST /login, use session cookie to access / and /dashboard, verify 200."""
    login_resp = await client.post(
        "/login",
        data={"username": TEST_USERNAME, "password": TEST_PASSWORD},
        follow_redirects=False,
    )
    assert login_resp.status_code == 303
    cookies = login_resp.cookies

    tracker_resp = await client.get("/", cookies=cookies)
    assert tracker_resp.status_code == 200
    assert "html" in tracker_resp.text.lower()

    dashboard_resp = await client.get("/dashboard", cookies=cookies)
    assert dashboard_resp.status_code == 200
    assert "html" in dashboard_resp.text.lower()


# --- Test c: Expired/missing session redirects to login ---

@pytest.mark.asyncio
async def test_expired_session_redirects(client):
    """Access / without session, verify redirect to /login."""
    resp = await client.get("/", follow_redirects=False)
    assert resp.status_code == 303
    assert "/login" in resp.headers["location"]

    resp = await client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 303
    assert "/login" in resp.headers["location"]


# --- Test d: API token works without session auth ---

@pytest.mark.asyncio
async def test_api_token_works_without_session(client):
    """Don't login, just use Bearer token on /api/runsheet/today, verify it works."""
    resp = await client.get(
        "/api/runsheet/today",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert "items" in data


# --- Test e: Wrong credentials stay on login page ---

@pytest.mark.asyncio
async def test_wrong_credentials_stays_on_login(client):
    """POST /login with wrong credentials, verify stays on login page."""
    resp = await client.post(
        "/login",
        data={"username": TEST_USERNAME, "password": "wrong-password-xyz"},
        follow_redirects=False,
    )
    assert resp.status_code == 200
    assert "login" in resp.text.lower()
    assert "Wrong username or password" in resp.text


# --- Test f: Runsheet static files serve ---

@pytest.mark.asyncio
async def test_runsheet_static_serves(client):
    """If runsheet/ directory exists, verify GET /runsheet/ returns 200."""
    resp = await client.get("/runsheet/")
    assert resp.status_code == 200
    assert "html" in resp.text.lower()


# --- Additional E2E scenarios ---

@pytest.mark.asyncio
async def test_complete_flow_login_to_api_create(client):
    """Complete flow: login -> session -> make API call with Bearer token."""
    login_resp = await client.post(
        "/login",
        data={"username": TEST_USERNAME, "password": TEST_PASSWORD},
        follow_redirects=False,
    )
    assert login_resp.status_code == 303
    cookies = login_resp.cookies

    page_resp = await client.get("/", cookies=cookies)
    assert page_resp.status_code == 200

    api_resp = await client.post(
        "/api/spending",
        json={"amount": 25.50, "category": "Groceries"},
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
    )
    assert api_resp.status_code == 201
    assert api_resp.json()["amount"] == 25.50


@pytest.mark.asyncio
async def test_api_no_auth_returns_401(client):
    resp = await client.post(
        "/api/spending",
        json={"amount": 10.00, "category": "Groceries"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_api_wrong_bearer_token_returns_401(client):
    resp = await client.post(
        "/api/spending",
        json={"amount": 10.00, "category": "Groceries"},
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_session_persists_across_requests(client):
    login_resp = await client.post(
        "/login",
        data={"username": TEST_USERNAME, "password": TEST_PASSWORD},
        follow_redirects=False,
    )
    cookies = login_resp.cookies

    for _ in range(3):
        resp = await client.get("/", cookies=cookies)
        assert resp.status_code == 200

    resp = await client.get("/dashboard", cookies=cookies)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_login_page_accessible_without_auth(client):
    resp = await client.get("/login")
    assert resp.status_code == 200
    assert "login" in resp.text.lower()
