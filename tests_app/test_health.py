"""GET /health with the database reachable, and the generic error handler (W-051)."""

from __future__ import annotations

from httpx import ASGITransport, AsyncClient


async def test_health_returns_200_with_database_reachable(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "database": "connected"}


async def test_unhandled_error_returns_generic_body_without_detail() -> None:
    from ofo_app.main import create_app

    app = create_app()
    leaked_detail = "internal detail: host db.internal port 5432"

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError(leaked_detail)

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/boom")
    assert response.status_code == 500
    body = response.json()
    assert body["error_class"] == "INTERNAL_SYSTEM"  # W-024 round 9 part 6: the catalogue's four parts
    assert all(body[part] for part in ("what_happened", "impact", "what_is_blocked", "next_action"))
    assert leaked_detail not in response.text
