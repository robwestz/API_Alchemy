"""End-to-end integration tests for Fas 2 manual adapter path.

Tests the full pipeline: fetch -> profile -> schema_inference
without any LLM calls. Uses a mock httpx response to avoid
network dependency in CI; real-API variant is gated behind
the OPEN_METEO_REAL_API=1 environment variable.

Run:
    pytest tests/integration/test_open_meteo_e2e.py -v
    pytest tests/integration/test_open_meteo_e2e.py -v -m integration
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from packages.adapters.open_meteo import OpenMeteoAdapter
from packages.lake.schema_inference import infer_schema
from packages.parser.profile import FieldProfile, profile_records

# ---------------------------------------------------------------------------
# Synthetic open-meteo response — mirrors real API structure exactly
# ---------------------------------------------------------------------------

_MOCK_RESPONSE: dict[str, Any] = {
    "latitude": 59.33,
    "longitude": 18.07,
    "generationtime_ms": 0.123,
    "utc_offset_seconds": 0,
    "timezone": "GMT",
    "timezone_abbreviation": "GMT",
    "elevation": 28.0,
    "current_units": {
        "time": "iso8601",
        "interval": "seconds",
        "temperature_2m": "°C",
        "relative_humidity_2m": "%",
        "wind_speed_10m": "km/h",
    },
    "current": {
        "time": "2026-04-29T10:00",
        "interval": 900,
        "temperature_2m": 14.2,
        "relative_humidity_2m": 65,
        "wind_speed_10m": 3.1,
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_httpx_response(data: dict[str, Any]) -> MagicMock:
    """Return a MagicMock that mimics an httpx.Response with JSON body."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value=data)
    return mock_resp


async def _collect_records(
    adapter: OpenMeteoAdapter, query: dict[str, Any]
) -> list[Any]:
    """Drain an async generator into a list."""
    records = []
    async for rec in adapter.fetch(query):
        records.append(rec)
    return records


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fetch_returns_at_least_one_record() -> None:
    """OpenMeteoAdapter.fetch() yields at least one Record with correct fields."""
    project_id = uuid4()
    adapter = OpenMeteoAdapter(project_id=project_id)

    mock_resp = _make_mock_httpx_response(_MOCK_RESPONSE)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        records = await _collect_records(
            adapter, {"latitude": "59.33", "longitude": "18.07"}
        )

    assert len(records) >= 1, "fetch() must yield at least one Record"

    rec = records[0]
    assert rec.adapter_name == "open_meteo"
    assert rec.adapter_version == "1.0.0"
    assert rec.project_id == project_id
    assert isinstance(rec.schema_hash, str) and len(rec.schema_hash) == 64
    assert isinstance(rec.payload, dict)
    assert "latitude" in rec.payload
    assert "current" in rec.payload
    assert rec.fetched_at is not None


@pytest.mark.integration
def test_manifest_returns_correct_name_and_version() -> None:
    """adapter.manifest() returns AdapterManifest with name=open_meteo, version=1.0.0."""
    adapter = OpenMeteoAdapter()
    manifest = adapter.manifest()

    assert manifest.name == "open_meteo"
    assert manifest.version == "1.0.0"
    assert manifest.model_used == "manual"
    assert manifest.secrets_required == []
    # status is an AdapterStatus enum; compare via value
    assert manifest.status.value == "active"


@pytest.mark.integration
def test_profile_records_infers_correct_types() -> None:
    """profile_records() infers correct Postgres types for open-meteo fields."""
    records = [_MOCK_RESPONSE]
    profiles = profile_records(records)

    assert len(profiles) > 0, "profiles must not be empty"

    # temperature_2m is a float -> real
    temp_key = "current.temperature_2m"
    assert temp_key in profiles, (
        f"expected {temp_key!r} in profiles, got: {list(profiles.keys())}"
    )
    assert profiles[temp_key].inferred_type == "real", (
        f"temperature_2m should be 'real', got {profiles[temp_key].inferred_type}"
    )

    # wind_speed_10m is a float -> real
    wind_key = "current.wind_speed_10m"
    assert wind_key in profiles
    assert profiles[wind_key].inferred_type == "real", (
        f"wind_speed_10m should be 'real', got {profiles[wind_key].inferred_type}"
    )

    # relative_humidity_2m is an int -> integer
    humidity_key = "current.relative_humidity_2m"
    assert humidity_key in profiles
    assert profiles[humidity_key].inferred_type == "integer", (
        f"relative_humidity_2m should be 'integer', "
        f"got {profiles[humidity_key].inferred_type}"
    )

    # latitude/longitude are floats -> real
    assert "latitude" in profiles
    assert profiles["latitude"].inferred_type == "real"

    # elevation is a float -> real
    assert "elevation" in profiles
    assert profiles["elevation"].inferred_type == "real"


@pytest.mark.integration
def test_infer_schema_contains_create_table() -> None:
    """infer_schema() returns SQL string containing CREATE TABLE."""
    profiles = profile_records([_MOCK_RESPONSE])
    sql = infer_schema("open_meteo", profiles)

    assert "CREATE TABLE" in sql, "SQL must contain CREATE TABLE"
    assert "open_meteo_records" in sql, "SQL must reference open_meteo_records table"


@pytest.mark.integration
def test_infer_schema_contains_standard_columns() -> None:
    """infer_schema() output includes all required standard columns."""
    profiles = profile_records([_MOCK_RESPONSE])
    sql = infer_schema("open_meteo", profiles)

    assert "id" in sql
    assert "project_id" in sql
    assert "fetched_at" in sql
    assert "adapter_version" in sql
    assert "schema_hash" in sql


@pytest.mark.integration
def test_infer_schema_contains_profile_columns() -> None:
    """infer_schema() output includes columns derived from the profiled fields."""
    profiles = profile_records([_MOCK_RESPONSE])
    sql = infer_schema("open_meteo", profiles)

    # Dot-notation flattened to underscore in SQL identifiers
    assert "latitude" in sql
    assert "longitude" in sql
    # current.temperature_2m -> current_temperature_2m
    assert "current_temperature_2m" in sql
    assert "current_wind_speed_10m" in sql


@pytest.mark.integration
@pytest.mark.asyncio
async def test_end_to_end_url_to_schema() -> None:
    """End-to-end: fetch -> profile -> infer_schema returns valid SQL without exception."""
    project_id = uuid4()
    adapter = OpenMeteoAdapter(project_id=project_id)

    mock_resp = _make_mock_httpx_response(_MOCK_RESPONSE)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        records = await _collect_records(
            adapter, {"latitude": "59.33", "longitude": "18.07"}
        )

    assert records, "fetch must return records"

    profiles = profile_records(records)
    assert profiles, "profile_records must return non-empty profiles"

    sql = infer_schema("open_meteo", profiles)

    assert "CREATE TABLE IF NOT EXISTS" in sql
    assert "open_meteo_records" in sql
    assert sql.strip().endswith(";")
    assert len(sql) > 100, f"SQL suspiciously short: {sql!r}"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fetch_with_real_api() -> None:
    """Optional: test against real open-meteo API when OPEN_METEO_REAL_API=1.

    Skipped by default — open-meteo is free and stable but CI should not
    depend on external network calls.
    """
    if not os.environ.get("OPEN_METEO_REAL_API"):
        pytest.skip("Set OPEN_METEO_REAL_API=1 to run against real API")

    adapter = OpenMeteoAdapter()
    records = await _collect_records(
        adapter, {"latitude": "59.33", "longitude": "18.07"}
    )

    assert len(records) >= 1
    rec = records[0]
    assert rec.adapter_name == "open_meteo"
    assert "current" in rec.payload or "hourly" in rec.payload
