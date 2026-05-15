import pytest


@pytest.mark.asyncio
async def test_healthcheck_returns_200(client):
    response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["data"]["db"] == "connected"
    assert response.json()["data"]["redis"] == "connected"
