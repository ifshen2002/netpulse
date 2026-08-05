"""Integration tests for auth enforcement and cross-project isolation.

Requires a running PostgreSQL with migrations applied.
Set NETPULSE_TESTING=1 to disable the scheduler during test runs.

Uses the `editor_ctx` fixture from conftest.py to provision authenticated users
without depending on bootstrap-admin semantics (which assume empty DB).
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from main import app

pytestmark = pytest.mark.anyio


def _uniq() -> str:
    return uuid.uuid4().hex[:12]


async def _register(client: AsyncClient, email: str, password: str, display_name: str) -> dict:
    resp = await client.post("/api/auth/register", json={
        "email": email, "password": password, "display_name": display_name,
    })
    assert resp.status_code == 201
    return resp.json()["data"]


# ── registration and session tests ──────────────────────────────


@pytest.mark.anyio
async def test_register_returns_session_token():
    """Registration returns a valid opaque session token."""
    email = f"reg_{_uniq()}@test.local"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/auth/register", json={
            "email": email, "password": "a-strong-password-123", "display_name": "Test User",
        })
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["access_token"] is not None
        assert data["token_type"] == "bearer"
        # 384 bits of entropy → ~48 base64url chars
        assert len(data["access_token"]) >= 40


@pytest.mark.anyio
async def test_duplicate_registration_rejected():
    """Registering the same email twice returns 409."""
    email = f"dup_{_uniq()}@test.local"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await _register(client, email, "a-strong-password-123", "Test")
        resp = await client.post("/api/auth/register", json={
            "email": email, "password": "a-strong-password-123", "display_name": "Test",
        })
        assert resp.status_code == 409


@pytest.mark.anyio
async def test_login_with_wrong_password_rejected():
    """Login with incorrect password returns 401."""
    email = f"badpw_{_uniq()}@test.local"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await _register(client, email, "correct-password-123", "Test")
        resp = await client.post("/api/auth/login", json={
            "email": email, "password": "wrong-password-000",
        })
        assert resp.status_code == 401


@pytest.mark.anyio
async def test_logout_revokes_session():
    """After logout, the session token is no longer valid."""
    email = f"logout_{_uniq()}@test.local"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        data = await _register(client, email, "a-strong-password-123", "Test")
        token = data["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Verify session works
        me = await client.get("/api/auth/me", headers=headers)
        assert me.status_code == 200

        # Logout
        logout = await client.post("/api/auth/logout", headers=headers)
        assert logout.status_code == 200

        # Session should be invalid now
        me2 = await client.get("/api/auth/me", headers=headers)
        assert me2.status_code == 401


# ── authorization enforcement tests ─────────────────────────────


@pytest.mark.anyio
async def test_unauthenticated_request_rejected():
    """Monitoring APIs return 401 when no token is provided."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        routes = [
            ("GET", "/api/nodes"),
            ("GET", "/api/endpoints"),
            ("GET", "/api/alerts"),
            ("GET", "/api/incidents"),
        ]
        for method, path in routes:
            resp = await client.request(method, path)
            assert resp.status_code == 401, f"{method} {path} should require auth"


@pytest.mark.anyio
async def test_health_check_is_public():
    """Health check does not require authentication."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["success"] is True


@pytest.mark.anyio
async def test_user_without_project_membership_cannot_access_monitoring():
    """A user without project membership gets 403 on project-scoped APIs."""
    email = f"lonely_{_uniq()}@test.local"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        data = await _register(client, email, "a-strong-password-123", "Lonely")
        token = data["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Without project membership, monitoring APIs should return 403
        endpoints = await client.get("/api/endpoints", headers=headers)
        assert endpoints.status_code == 403, f"Expected 403, got {endpoints.status_code}"
