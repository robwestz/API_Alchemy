"""Smoke-tester for Gateway och LakeRepository.

Markerade @pytest.mark.integration - kraver en korande Postgres-instans.
Om TEST_DATABASE_URL ej ar satt i miljon hoppas testerna over med
tydligt meddelande.

Kor:
    pytest tests/integration/test_smoke.py -v
"""

from __future__ import annotations

import os
import pathlib

import httpx
import pytest
import pytest_asyncio

# ---------------------------------------------------------------------------
# DB-fixture: skapar tabeller via 001_initial.sql, river efter testet
# ---------------------------------------------------------------------------

TEST_DSN = os.environ.get("TEST_DATABASE_URL", "")

SKIP_REASON = (
    "TEST_DATABASE_URL not set - skipping integration tests. "
    "Set TEST_DATABASE_URL=postgres://user:pass@host/testdb to run."
)


@pytest_asyncio.fixture(scope="session")
async def db_repo():  # type: ignore[return]
    """Startar LakeRepository mot test-DB och kor migrations."""
    if not TEST_DSN:
        pytest.skip(SKIP_REASON)

    from packages.lake.repository import LakeRepository

    repo = LakeRepository()
    await repo.connect(TEST_DSN)

    # Kor 001_initial.sql for att skapa tabeller
    sql_path = (
        pathlib.Path(__file__).parent.parent.parent
        / "packages"
        / "lake"
        / "migrations"
        / "001_initial.sql"
    )
    sql = sql_path.read_text(encoding="utf-8")
    async with repo._get_pool().acquire() as conn:
        await conn.execute(sql)

    yield repo

    await repo.close()


@pytest_asyncio.fixture
async def client(db_repo):  # type: ignore[return]
    """httpx.AsyncClient mot ASGI-app med injektad repo."""
    from packages.gateway.main import _repo, app, settings

    settings.database_url = TEST_DSN

    if _repo._pool is None:
        await _repo.connect(TEST_DSN)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_health(client: httpx.AsyncClient) -> None:
    """GET /health ska returnera 200 med status ok."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_projects_roundtrip(client: httpx.AsyncClient) -> None:
    """POST /api/projects + GET /api/projects roundtrip."""
    create_resp = await client.post("/api/projects", json={"name": "smoke-test-project"})
    assert create_resp.status_code == 201, create_resp.text
    created = create_resp.json()
    assert created["name"] == "smoke-test-project"
    assert "id" in created

    project_id = created["id"]

    list_resp = await client.get("/api/projects")
    assert list_resp.status_code == 200
    projects = list_resp.json()
    ids = [p["id"] for p in projects]
    assert project_id in ids

    get_resp = await client.get(f"/api/projects/{project_id}")
    assert get_resp.status_code == 200
    fetched = get_resp.json()
    assert fetched["id"] == project_id
    assert fetched["name"] == "smoke-test-project"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tools_contains_health_check(client: httpx.AsyncClient) -> None:
    """GET /api/tools ska returnera dict med minst health_check."""
    response = await client.get("/api/tools")
    assert response.status_code == 200
    tools = response.json()
    assert isinstance(tools, dict)
    assert "health_check" in tools
    hc = tools["health_check"]
    assert hc["name"] == "health_check"
    assert "input_schema" in hc
    assert "output_schema" in hc


@pytest.mark.integration
@pytest.mark.asyncio
async def test_execute_health_check_tool(client: httpx.AsyncClient) -> None:
    """POST /api/tools/health_check ska returnera status ok."""
    response = await client.post("/api/tools/health_check", json={})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "ts" in data


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tool_not_found(client: httpx.AsyncClient) -> None:
    """POST /api/tools/nonexistent ska returnera 404."""
    response = await client.post("/api/tools/nonexistent_tool_xyz", json={})
    assert response.status_code == 404
