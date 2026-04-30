"""Open-Meteo adapter — manuell implementation (Fas 2 proof of plumbing).

Hämtar väderdata från https://api.open-meteo.com/v1/forecast (gratis, ingen API-key).
Implementerar BaseAdapter-kontraktet från packages/interfaces/__init__.py.

Per DECISIONS.md D7: varje adapter-version har ett manifest.json med schema_hash.
Inga API-specifika if-satser i orchestrator — denna adapter är specifik per definition.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
from loguru import logger

from packages.interfaces import (
    AdapterManifest,
    AdapterStatus,
    BaseAdapter,
    Record,
    SecretsResolver,
)

__all__ = ["OpenMeteoAdapter"]

_MANIFEST_PATH = Path(__file__).parent / "manifest.json"

# Base URL — query params are passed by caller (or defaulted in fetch())
_BASE_URL = "https://api.open-meteo.com/v1/forecast"

# Default query fields when caller does not supply them
_DEFAULT_PARAMS: dict[str, str] = {
    "current": "temperature_2m,relative_humidity_2m,wind_speed_10m",
}

_ADAPTER_NAME = "open_meteo"
_ADAPTER_VERSION = "1.0.0"


def _compute_schema_hash(data: dict[str, Any]) -> str:
    """Compute a deterministic SHA-256 hash of the response key structure.

    Hash is derived from sorted dot-notation key paths (keys only, not values)
    so that records with the same schema but different values share the same
    hash — stable across re-fetches.
    """
    key_structure = sorted(_extract_key_paths(data))
    canonical = json.dumps(key_structure, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _extract_key_paths(obj: Any, prefix: str = "") -> list[str]:
    """Recursively extract dot-notation key paths from a nested dict."""
    paths: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            full_key = f"{prefix}.{k}" if prefix else k
            paths.append(full_key)
            paths.extend(_extract_key_paths(v, full_key))
    elif isinstance(obj, list) and obj:
        # Inspect first element to capture schema shape
        paths.extend(_extract_key_paths(obj[0], prefix))
    return paths


def _build_params(query: dict[str, Any]) -> dict[str, str]:
    """Merge caller-supplied query params with defaults; return flat string dict."""
    merged: dict[str, str] = {}

    # Apply defaults first, then caller overrides
    for k, v in _DEFAULT_PARAMS.items():
        merged[k] = str(v)

    for k, v in query.items():
        merged[k] = str(v)

    # Ensure lat/lon are always present
    if "latitude" not in merged or "longitude" not in merged:
        logger.warning(
            "OpenMeteoAdapter: latitude/longitude not supplied; "
            "defaulting to Stockholm (59.33, 18.07)"
        )
        merged.setdefault("latitude", "59.33")
        merged.setdefault("longitude", "18.07")

    return merged


class OpenMeteoAdapter(BaseAdapter):
    """Manual adapter for https://api.open-meteo.com/v1/forecast.

    Requires no API key — open-meteo is a free public API.

    Usage::

        adapter = OpenMeteoAdapter()
        async for record in adapter.fetch({"latitude": "59.33", "longitude": "18.07"}):
            print(record.payload)
    """

    name: str = _ADAPTER_NAME
    version: str = _ADAPTER_VERSION
    schema_hash: str = ""  # computed per-response in fetch()
    secrets_required: list[str] = []

    def __init__(self, project_id: UUID | None = None) -> None:
        self._project_id: UUID = project_id if project_id is not None else uuid4()
        logger.debug(
            f"OpenMeteoAdapter initialised "
            f"project_id={self._project_id} version={_ADAPTER_VERSION}"
        )

    # ------------------------------------------------------------------
    # BaseAdapter contract
    # ------------------------------------------------------------------

    def fetch(  # type: ignore[override]
        self,
        query: dict[str, Any],
        secrets: SecretsResolver | None = None,
    ) -> AsyncIterator[Record]:
        """Return an async iterator that fetches weather data and yields Records.

        `query` may contain any open-meteo query params
        (latitude, longitude, current, hourly, …).
        Missing latitude/longitude are defaulted to Stockholm.

        `secrets` is ignored — open-meteo requires no authentication.
        """
        return self._fetch_generator(query)

    async def _fetch_generator(
        self,
        query: dict[str, Any],
    ) -> AsyncIterator[Record]:
        params = _build_params(query)
        logger.info(f"OpenMeteoAdapter: GET {_BASE_URL} params={params}")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(_BASE_URL, params=params)
            response.raise_for_status()
            data: dict[str, Any] = response.json()

        logger.debug(f"OpenMeteoAdapter: response keys={list(data.keys())}")

        schema_hash = _compute_schema_hash(data)
        fetched_at = datetime.now(tz=timezone.utc)

        record = Record(
            project_id=self._project_id,
            adapter_name=_ADAPTER_NAME,
            adapter_version=_ADAPTER_VERSION,
            schema_hash=schema_hash,
            payload=data,
            fetched_at=fetched_at,
            lineage={
                "source_url": _BASE_URL,
                "params": params,
                "fetched_at": fetched_at.isoformat(),
            },
        )
        logger.info(
            f"OpenMeteoAdapter: yielding record schema_hash={schema_hash[:12]}…"
        )
        yield record

    def manifest(self) -> AdapterManifest:
        """Load and return the adapter manifest from manifest.json."""
        raw = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
        return AdapterManifest(
            name=raw["name"],
            version=raw["version"],
            schema_hash=raw["schema_hash"],
            doc_url=raw["doc_url"],
            generated_at=datetime.fromisoformat(
                raw["generated_at"].replace("Z", "+00:00")
            ),
            model_used=raw["model_used"],
            prompts_used=raw.get("prompts_used", []),
            secrets_required=raw.get("secrets_required", []),
            status=AdapterStatus(raw.get("status", "active")),
        )
