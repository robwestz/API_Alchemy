"""Data Lake repository — asyncpg connection pool + typed query methods.

Enda platsen som pratar direkt med Postgres. Alla andra paket importerar
denna klass och kör queries via den.

mypy strict-kompatibel. Inga direkta os.environ-anrop — DSN skickas in
som argument från config-modulen.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import asyncpg
from loguru import logger
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Pydantic model
# ---------------------------------------------------------------------------


class Project(BaseModel):
    """Representation av en rad i `projects`-tabellen."""

    id: UUID
    name: str
    created_at: datetime
    daily_cap_usd: float = Field(default=5.0)
    monthly_cap_usd: float = Field(default=50.0)


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class LakeRepository:
    """Asyncpg-baserad repository för Universal Data Lake.

    Användning::

        repo = LakeRepository()
        await repo.connect(dsn="postgres://user:pass@host/db")
        project = await repo.create_project("my-project")
        await repo.close()

    FastAPI-integrering sker via Depends (se packages/gateway/main.py).
    """

    def __init__(self) -> None:
        self._pool: asyncpg.Pool[asyncpg.Record] | None = None

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self, dsn: str) -> None:
        """Öppna connection pool. Anropas vid app startup."""
        logger.info("LakeRepository: connecting to Postgres")
        self._pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=10)
        logger.info("LakeRepository: pool ready")

    async def close(self) -> None:
        """Stäng connection pool. Anropas vid app shutdown."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            logger.info("LakeRepository: pool closed")

    def _get_pool(self) -> asyncpg.Pool[asyncpg.Record]:
        if self._pool is None:
            raise RuntimeError("LakeRepository not connected — call connect() first")
        return self._pool

    # ------------------------------------------------------------------
    # Generic query helpers
    # ------------------------------------------------------------------

    async def execute(self, sql: str, *args: Any) -> str:
        """Kör en write-query och returnera statussträngen från Postgres."""
        pool = self._get_pool()
        async with pool.acquire() as conn:
            result: str = await conn.execute(sql, *args)
            return result

    async def fetch(self, sql: str, *args: Any) -> list[asyncpg.Record]:
        """Hämta alla rader som matchar query."""
        pool = self._get_pool()
        async with pool.acquire() as conn:
            rows: list[asyncpg.Record] = await conn.fetch(sql, *args)
            return rows

    async def fetchrow(self, sql: str, *args: Any) -> asyncpg.Record | None:
        """Hämta en rad eller None."""
        pool = self._get_pool()
        async with pool.acquire() as conn:
            row: asyncpg.Record | None = await conn.fetchrow(sql, *args)
            return row

    # ------------------------------------------------------------------
    # Project methods
    # ------------------------------------------------------------------

    async def create_project(self, name: str) -> Project:
        """Skapa ett nytt projekt och returnera det som Pydantic-modell."""
        row = await self.fetchrow(
            """
            INSERT INTO projects (name)
            VALUES ($1)
            RETURNING id, name, created_at, daily_cap_usd, monthly_cap_usd
            """,
            name,
        )
        if row is None:
            raise RuntimeError(f"Failed to create project '{name}'")
        project = _row_to_project(row)
        logger.info(f"Created project id={project.id} name={project.name!r}")
        return project

    async def list_projects(self) -> list[Project]:
        """Returnera alla projekt, nyaste först."""
        rows = await self.fetch(
            "SELECT id, name, created_at, daily_cap_usd, monthly_cap_usd "
            "FROM projects ORDER BY created_at DESC"
        )
        return [_row_to_project(r) for r in rows]

    async def get_project(self, project_id: UUID) -> Project | None:
        """Hämta ett specifikt projekt eller None."""
        row = await self.fetchrow(
            "SELECT id, name, created_at, daily_cap_usd, monthly_cap_usd "
            "FROM projects WHERE id = $1",
            project_id,
        )
        if row is None:
            return None
        return _row_to_project(row)

    # ------------------------------------------------------------------
    # Tool call logging
    # ------------------------------------------------------------------

    async def record_tool_call(
        self,
        *,
        project_id: UUID,
        tool_name: str,
        model: str,
        prompt: str | None = None,
        temperature: float | None = None,
        seed: int | None = None,
        input_hash: str | None = None,
        output_hash: str | None = None,
    ) -> None:
        """Logga ett tool-anrop till `tool_calls_log` för reproducibility."""
        await self.execute(
            """
            INSERT INTO tool_calls_log
                (project_id, tool_name, prompt, model, temperature, seed, input_hash, output_hash)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            project_id,
            tool_name,
            prompt,
            model,
            temperature,
            seed,
            input_hash,
            output_hash,
        )
        logger.debug(f"Logged tool_call tool={tool_name!r} project={project_id}")

    # ------------------------------------------------------------------
    # Cost ledger
    # ------------------------------------------------------------------

    async def record_cost(
        self,
        *,
        project_id: UUID,
        agent_id: str,
        model: str,
        tokens_in: int,
        tokens_out: int,
        cost_usd: float,
    ) -> None:
        """Skriv ett LLM-kostnadsrad till `cost_ledger`."""
        await self.execute(
            """
            INSERT INTO cost_ledger
                (project_id, agent_id, model, tokens_in, tokens_out, cost_usd)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            project_id,
            agent_id,
            model,
            tokens_in,
            tokens_out,
            cost_usd,
        )
        logger.debug(
            f"Recorded cost agent={agent_id!r} model={model!r} "
            f"cost_usd={cost_usd:.6f} project={project_id}"
        )

    # ------------------------------------------------------------------
    # Event emission
    # ------------------------------------------------------------------

    async def emit_event(
        self,
        *,
        project_id: UUID,
        kind: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Appenda ett immutable event till `events`-tabellen."""
        await self.execute(
            "INSERT INTO events (project_id, kind, payload) VALUES ($1, $2, $3)",
            project_id,
            kind,
            json.dumps(payload or {}),
        )
        logger.debug(f"Emitted event kind={kind!r} project={project_id}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_project(row: asyncpg.Record) -> Project:
    """Konvertera en asyncpg Record till Project Pydantic-modell."""
    created_at: datetime = row["created_at"]
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return Project(
        id=row["id"],
        name=row["name"],
        created_at=created_at,
        daily_cap_usd=float(row["daily_cap_usd"]),
        monthly_cap_usd=float(row["monthly_cap_usd"]),
    )
