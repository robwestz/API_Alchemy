"""Gateway — FastAPI-app, localhost-only, ingen logik utöver routing.

Lyssnar på 127.0.0.1 (single-user, D5). Alla endpoints delegerar till
primitives i TOOL_REGISTRY eller LakeRepository. Inga LLM-anrop här.

Starta:
    uvicorn packages.gateway.main:app --host 127.0.0.1 --port 8000 --reload
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

from packages.lake.repository import LakeRepository, Project
from packages.orchestrator.primitives._registry import TOOL_REGISTRY


# ---------------------------------------------------------------------------
# Config (läser .env via pydantic-settings — aldrig os.environ direkt)
# ---------------------------------------------------------------------------


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = ""
    log_level: str = "INFO"


settings = Settings()


# ---------------------------------------------------------------------------
# WebSocket connection manager
# ---------------------------------------------------------------------------


class ConnectionManager:
    """Håller aktiva WebSocket-anslutningar per project_id topic."""

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def connect(self, project_id: str, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections[project_id].append(ws)
        logger.info(f"WS connect project={project_id}")

    async def disconnect(self, project_id: str, ws: WebSocket) -> None:
        async with self._lock:
            conns = self._connections.get(project_id, [])
            if ws in conns:
                conns.remove(ws)
        logger.info(f"WS disconnect project={project_id}")

    async def broadcast(self, project_id: str, message: dict[str, Any]) -> None:
        async with self._lock:
            targets = list(self._connections.get(project_id, []))
        for ws in targets:
            try:
                await ws.send_json(message)
            except Exception as exc:
                logger.warning(f"WS send failed project={project_id}: {exc}")


manager = ConnectionManager()


# ---------------------------------------------------------------------------
# Shared LakeRepository instance (lifecycle managed via lifespan)
# ---------------------------------------------------------------------------

_repo = LakeRepository()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup: connect DB pool. Shutdown: close pool."""
    if settings.database_url:
        await _repo.connect(settings.database_url)
    else:
        logger.warning(
            "DATABASE_URL not set — DB features disabled. "
            "Set DATABASE_URL in .env to enable persistence."
        )
    yield
    await _repo.close()


def get_repo() -> LakeRepository:
    """FastAPI dependency — injectad i alla endpoints som behöver DB."""
    return _repo


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="API Alchemy Engine",
    version="0.1.0",
    description="Autonom motor: ide -> dataprodukt via agent-svarm.",
    lifespan=lifespan,
)

# localhost-only CORS (single-user, D5)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class CreateProjectRequest(BaseModel):
    name: str


class ToolListItem(BaseModel):
    """Serialiserbar representation av ToolSpec (utan handler callable)."""

    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    agent_allowed: bool
    ui_visible: bool
    ui_component: str | None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict[str, str]:
    """Smoke-test endpoint. Används av CI och monitoring."""
    return {"status": "ok", "version": "0.1.0"}


@app.get("/api/tools", response_model=dict[str, ToolListItem])
async def list_tools() -> dict[str, ToolListItem]:
    """Returnera alla registrerade primitives utan handler (ej JSON-serialiserbart).

    Frontend-build och agent-runtime konsumerar detta för action parity.
    """
    result: dict[str, ToolListItem] = {}
    for name, spec in TOOL_REGISTRY.items():
        result[name] = ToolListItem(
            name=spec.name,
            description=spec.description,
            input_schema=spec.input_schema.model_json_schema(),
            output_schema=spec.output_schema.model_json_schema(),
            agent_allowed=spec.agent_allowed,
            ui_visible=spec.ui_visible,
            ui_component=spec.ui_component,
        )
    return result


@app.post("/api/projects", response_model=Project, status_code=201)
async def create_project(
    body: CreateProjectRequest,
    repo: LakeRepository = Depends(get_repo),
) -> Project:
    """Skapa ett nytt projekt. Returnerar Project med genererat UUID."""
    try:
        project = await repo.create_project(body.name)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    # Broadcast event till eventuella WS-subscribers
    await manager.broadcast(
        str(project.id),
        {"event": "project:created", "project_id": str(project.id)},
    )
    return project


@app.get("/api/projects", response_model=list[Project])
async def list_projects(
    repo: LakeRepository = Depends(get_repo),
) -> list[Project]:
    """Lista alla projekt, nyaste först."""
    return await repo.list_projects()


@app.get("/api/projects/{project_id}", response_model=Project)
async def get_project(
    project_id: UUID,
    repo: LakeRepository = Depends(get_repo),
) -> Project:
    """Hamta ett specifikt projekt eller 404."""
    project = await repo.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    return project


@app.post("/api/tools/{name}")
async def execute_tool(
    name: str,
    body: dict[str, Any],
    repo: LakeRepository = Depends(get_repo),
) -> Any:
    """Exekvera en registrerad primitive.

    Body valideras mot ToolSpec.input_schema. Output loggas till tool_calls_log.
    Samma handler som agenter anropar — action parity per ARCHITECTURE.md sektion 5.
    """
    spec = TOOL_REGISTRY.get(name)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"Tool '{name}' not found")

    # Validera input mot ToolSpec.input_schema
    try:
        validated_input = spec.input_schema.model_validate(body)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Kor handler
    try:
        output = await spec.handler(validated_input)
    except Exception as exc:
        logger.exception(f"Tool handler failed: tool={name!r}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    output_dict: dict[str, Any] = (
        output.model_dump() if hasattr(output, "model_dump") else {}
    )

    # Logga till tool_calls_log — project_id ar valfritt pa rotniva
    input_hash = hashlib.sha256(
        json.dumps(body, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]
    output_hash = hashlib.sha256(
        json.dumps(output_dict, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]

    project_id_raw = body.get("project_id")
    if project_id_raw and repo._pool is not None:
        try:
            await repo.record_tool_call(
                project_id=UUID(str(project_id_raw)),
                tool_name=name,
                model="n/a",
                input_hash=input_hash,
                output_hash=output_hash,
            )
        except Exception as exc:
            logger.warning(f"Failed to log tool_call: {exc}")

    return output_dict


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------


@app.websocket("/ws/projects/{project_id}")
async def websocket_project(
    project_id: str,
    websocket: WebSocket,
) -> None:
    """WebSocket-kanal for ett projekts events (topic: project:<id>).

    UI och agenter subscribe:ar pa samma kanal — delat state per
    ARCHITECTURE.md sektion 5.
    """
    await manager.connect(project_id, websocket)
    try:
        while True:
            # Hall anslutningen vid liv; klienten kan skicka ping
            data = await websocket.receive_text()
            logger.debug(f"WS recv project={project_id} data={data!r}")
    except WebSocketDisconnect:
        await manager.disconnect(project_id, websocket)
