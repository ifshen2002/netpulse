import os
import uuid

os.environ["NETPULSE_TESTING"] = "1"

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

import db  # noqa: E402
import redis_client  # noqa: E402
from main import app  # noqa: E402


def _new_client() -> AsyncClient:
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def _make_admin_and_editor() -> dict:
    """Create one admin + one editor with project membership. Returns dict."""
    suffix = uuid.uuid4().hex[:8]
    admin_email = f"test-admin-{suffix}@netpulse.test"
    editor_email = f"test-editor-{suffix}@netpulse.test"
    password = "test-pw-strong-123"

    async with _new_client() as ac:
        # Register admin
        reg = await ac.post("/api/auth/register", json={
            "email": admin_email, "password": password, "display_name": "Test Admin",
        })
        assert reg.status_code == 201, f"admin register failed: {reg.text}"
        admin_id = reg.json()["data"]["user"]["id"]

        # Promote via SQL
        async with db.engine.begin() as conn:
            await conn.execute(
                text("UPDATE users SET is_platform_admin = true WHERE id = :id"),
                {"id": admin_id},
            )

        # Re-login
        login = await ac.post("/api/auth/login", json={
            "email": admin_email, "password": password,
        })
        assert login.status_code == 200
        admin_token = login.json()["data"]["access_token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        # Org + project
        org_resp = await ac.post(
            "/api/admin/organizations",
            json={"name": f"TestOrg-{suffix}"}, headers=admin_headers,
        )
        assert org_resp.status_code == 201
        org_id = org_resp.json()["data"]["id"]
        proj_resp = await ac.post(
            "/api/admin/projects",
            json={"organization_id": org_id, "name": f"TestProj-{suffix}"},
            headers=admin_headers,
        )
        assert proj_resp.status_code == 201
        project_id = proj_resp.json()["data"]["id"]

        # Register editor + approve
        reg2 = await ac.post("/api/auth/register", json={
            "email": editor_email, "password": password, "display_name": "Test Editor",
        })
        assert reg2.status_code == 201
        editor_token = reg2.json()["data"]["access_token"]

        ar = await ac.post(
            "/api/access-requests",
            json={"project_id": project_id, "requested_role": "editor", "reason": "test"},
            headers={"Authorization": f"Bearer {editor_token}"},
        )
        assert ar.status_code == 201
        ar_id = ar.json()["data"]["id"]
        await ac.post(
            f"/api/admin/access-requests/{ar_id}/review",
            json={"decision": "approved"}, headers=admin_headers,
        )

    return {
        "admin_headers": admin_headers,
        "editor_headers": {
            "Authorization": f"Bearer {editor_token}",
            "X-Project-ID": project_id,
        },
    }


@pytest_asyncio.fixture
async def client():
    """Unauthenticated HTTP client."""
    async with _new_client() as c:
        yield c


@pytest_asyncio.fixture(autouse=True)
async def _fresh_redis_for_test():
    """Replace redis_client.client with a fresh instance per test.
    All modules now use `redis_client.client.xxx()` (dynamic access), so
    swapping the module-level attribute updates everyone."""
    old = redis_client.client
    redis_client.client = redis_client.aioredis.Redis.from_url(os.environ["REDIS_URL"])
    yield
    try:
        await redis_client.client.aclose()
    except Exception:
        pass
    redis_client.client = old


@pytest_asyncio.fixture
async def editor_headers():
    """Auth + X-Project-ID headers for an editor."""
    return (await _make_admin_and_editor())["editor_headers"]


@pytest_asyncio.fixture
async def editor_headers_no_project():
    """Auth-only headers (no X-Project-ID). For V1 global queries."""
    ctx = await _make_admin_and_editor()
    return {"Authorization": ctx["editor_headers"]["Authorization"]}


@pytest_asyncio.fixture
async def admin_headers():
    """Authorization headers for a platform_admin."""
    return (await _make_admin_and_editor())["admin_headers"]
