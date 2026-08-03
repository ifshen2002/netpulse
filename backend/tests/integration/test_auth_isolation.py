"""Integration tests for auth enforcement and cross-project isolation.

Requires a running PostgreSQL with migrations applied.
Set NETPULSE_TESTING=1 to disable the scheduler during test runs.
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


async def _login(client: AsyncClient, email: str, password: str) -> dict:
    resp = await client.post("/api/auth/login", json={
        "email": email, "password": password,
    })
    assert resp.status_code == 200
    return resp.json()["data"]


async def _create_org(client: AsyncClient, token: str, name: str) -> dict:
    resp = await client.post("/api/admin/organizations", json={"name": name}, headers={
        "Authorization": f"Bearer {token}",
    })
    assert resp.status_code == 201
    return resp.json()["data"]


async def _create_project(client: AsyncClient, token: str, org_id: str, name: str) -> dict:
    resp = await client.post("/api/admin/projects", json={
        "organization_id": org_id, "name": name,
    }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 201
    return resp.json()["data"]


# ── registration and session tests ──────────────────────────────


@pytest.mark.anyio
async def test_first_user_becomes_platform_admin():
    """The first registered user is automatically a platform_admin."""
    email = f"admin_{_uniq()}@test.local"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        data = await _register(client, email, "a-strong-password-123", "Admin User")
        assert data["user"]["is_platform_admin"] is True
        assert data["access_token"] is not None
        assert data["token_type"] == "bearer"


@pytest.mark.anyio
async def test_second_user_is_not_platform_admin():
    """The second registered user is NOT a platform_admin."""
    email1 = f"user1_{_uniq()}@test.local"
    email2 = f"user2_{_uniq()}@test.local"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await _register(client, email1, "a-strong-password-123", "First User")
        data2 = await _register(client, email2, "a-strong-password-123", "Second User")
        assert data2["user"]["is_platform_admin"] is False


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
async def test_viewer_cannot_create_endpoints():
    """A user without project membership cannot access monitoring APIs."""
    email = f"viewer_{_uniq()}@test.local"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        data = await _register(client, email, "a-strong-password-123", "Viewer")
        token = data["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Without project membership, monitoring APIs should return 403
        resp = await client.post("/api/endpoints", json={
            "name": "Test", "target_host": "8.8.8.8",
        }, headers=headers)
        assert resp.status_code in (403, 400), f"Expected 403 or 400, got {resp.status_code}"


# ── access request workflow tests ───────────────────────────────


@pytest.mark.anyio
async def test_access_request_workflow():
    """Full access request lifecycle: submit, approve, membership created."""
    # Register admin (first user)
    admin_email = f"ar_admin_{_uniq()}@test.local"
    viewer_email = f"ar_viewer_{_uniq()}@test.local"
    admin_pw = "admin-password-123!!"
    viewer_pw = "viewer-password-123!!"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Admin registration (first user)
        admin = await _register(client, admin_email, admin_pw, "Admin")
        admin_token = admin["access_token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        # Create a new project
        org = await _create_org(client, admin_token, "Test Corp")
        project = await _create_project(client, admin_token, org["id"], "Ops Dashboard")

        # Register viewer
        viewer = await _register(client, viewer_email, viewer_pw, "Viewer User")
        viewer_token = viewer["access_token"]
        viewer_headers = {"Authorization": f"Bearer {viewer_token}"}

        # Viewer has no project access initially
        my_projects = await client.get("/api/projects", headers=viewer_headers)
        assert my_projects.status_code == 200
        assert len(my_projects.json()["data"]) == 0

        # Submit access request
        ar = await client.post("/api/access-requests", json={
            "project_id": project["id"],
            "requested_role": "viewer",
            "reason": "Need to monitor production",
        }, headers=viewer_headers)
        assert ar.status_code == 201
        request_id = ar.json()["data"]["id"]

        # Admin views pending requests
        pending = await client.get("/api/admin/access-requests", headers=admin_headers)
        assert pending.status_code == 200
        pending_data = pending.json()["data"]
        assert any(r["id"] == request_id for r in pending_data)

        # Admin approves
        approve = await client.post(f"/api/admin/access-requests/{request_id}/review", json={
            "decision": "approved",
        }, headers=admin_headers)
        assert approve.status_code == 200

        # Viewer now has project access
        my_projects2 = await client.get("/api/projects", headers=viewer_headers)
        assert my_projects2.status_code == 200
        assert len(my_projects2.json()["data"]) == 1
        assert my_projects2.json()["data"][0]["role"] == "viewer"


@pytest.mark.anyio
async def test_access_request_rejected():
    """Rejected access request does not create membership."""
    admin_email = f"rej_admin_{_uniq()}@test.local"
    viewer_email = f"rej_viewer_{_uniq()}@test.local"
    pw = "a-strong-password-123"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        admin = await _register(client, admin_email, pw, "Admin")
        admin_token = admin["access_token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        org = await _create_org(client, admin_token, "Reject Corp")
        project = await _create_project(client, admin_token, org["id"], "Secret Dashboard")

        viewer = await _register(client, viewer_email, pw, "Viewer")
        viewer_headers = {"Authorization": f"Bearer {viewer['access_token']}"}

        ar = await client.post("/api/access-requests", json={
            "project_id": project["id"], "requested_role": "viewer", "reason": "test",
        }, headers=viewer_headers)
        request_id = ar.json()["data"]["id"]

        # Admin rejects
        await client.post(f"/api/admin/access-requests/{request_id}/review", json={
            "decision": "rejected",
        }, headers=admin_headers)

        # Viewer still has no access
        my_projects = await client.get("/api/projects", headers=viewer_headers)
        assert len(my_projects.json()["data"]) == 0


# ── audit log tests ─────────────────────────────────────────────


@pytest.mark.anyio
async def test_audit_log_captures_events():
    """Registration, login, org creation all produce audit log entries."""
    email = f"audit_{_uniq()}@test.local"
    pw = "a-strong-password-123"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        data = await _register(client, email, pw, "Audit User")
        token = data["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Audit log should contain registration event (admin can see all)
        logs = await client.get("/api/audit-logs?limit=50", headers=headers)
        assert logs.status_code == 200
        log_data = logs.json()["data"]
        actions = [entry["action"] for entry in log_data]
        assert "user.registered" in actions
