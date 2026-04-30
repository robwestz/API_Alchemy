"""Deterministisk fält-profilering — inga LLM-anrop.

Tar en lista av dicts eller Record-objekt, flattar nested strukturer till
dot-notation och producerar ett FieldProfile per fält med inferred Postgres-typ,
null-rate, unique count och sample values.
"""

from __future__ import annotations

from typing import Any

from loguru import logger
from pydantic import BaseModel, Field

# Lazy import to avoid circular deps — Record is only used for isinstance check
_RECORD_TYPE: type | None = None


def _get_record_type() -> type:
    global _RECORD_TYPE  # noqa: PLW0603
    if _RECORD_TYPE is None:
        from packages.interfaces import Record  # noqa: PLC0415

        _RECORD_TYPE = Record
    return _RECORD_TYPE


__all__ = ["FieldProfile", "profile_records"]

# Maximum number of sample values stored per field
_MAX_SAMPLES = 5


class FieldProfile(BaseModel):
    """Profile for a single field across a collection of records.

    `inferred_type` is a Postgres type string:
    text, integer, real, boolean, jsonb, timestamptz.
    """

    name: str
    inferred_type: str  # text | integer | real | boolean | jsonb | timestamptz
    null_rate: float = Field(ge=0.0, le=1.0)
    unique_count: int = Field(ge=0)
    sample_values: list[Any] = Field(default_factory=list)
    min_value: Any | None = None
    max_value: Any | None = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def profile_records(
    records: list[dict[str, Any]] | list[Any],
) -> dict[str, FieldProfile]:
    """Profile a list of records and return a FieldProfile per dot-notation field.

    Accepts either plain dicts or Record Pydantic objects (the payload is used).
    Nested dicts are flattened to dot-notation keys.
    No LLM calls — purely deterministic Python logic.
    """
    if not records:
        logger.warning("profile_records: empty records list — returning empty profiles")
        return {}

    Record = _get_record_type()

    # Normalise to list of flat dicts
    flat_dicts: list[dict[str, Any]] = []
    for rec in records:
        if isinstance(rec, Record):
            flat_dicts.append(_flatten(rec.payload))  # type: ignore[union-attr]
        elif isinstance(rec, dict):
            flat_dicts.append(_flatten(rec))
        else:
            # Best-effort: try .payload attribute, else skip
            payload = getattr(rec, "payload", None)
            if payload and isinstance(payload, dict):
                flat_dicts.append(_flatten(payload))
            else:
                logger.warning(
                    f"profile_records: skipping unrecognised record type {type(rec)}"
                )

    if not flat_dicts:
        return {}

    total = len(flat_dicts)

    # Collect all field names across all records
    all_keys: set[str] = set()
    for d in flat_dicts:
        all_keys.update(d.keys())

    logger.debug(f"profile_records: {total} records, {len(all_keys)} unique fields")

    profiles: dict[str, FieldProfile] = {}

    for key in sorted(all_keys):
        values_all: list[Any] = [d.get(key) for d in flat_dicts]
        non_null = [v for v in values_all if v is not None]
        null_count = total - len(non_null)
        null_rate = null_count / total if total > 0 else 0.0

        unique_count = len({_hashable(v) for v in non_null})

        # Samples — up to _MAX_SAMPLES distinct values
        seen: set[Any] = set()
        samples: list[Any] = []
        for v in non_null:
            hv = _hashable(v)
            if hv not in seen:
                seen.add(hv)
                samples.append(v)
            if len(samples) >= _MAX_SAMPLES:
                break

        # min/max — only for orderable scalar types
        min_val: Any | None = None
        max_val: Any | None = None
        orderable = [v for v in non_null if isinstance(v, (int, float, str))]
        if orderable:
            try:
                min_val = min(orderable)
                max_val = max(orderable)
            except TypeError:
                pass  # mixed types — skip

        inferred = _infer_postgres_type(non_null, key)

        profiles[key] = FieldProfile(
            name=key,
            inferred_type=inferred,
            null_rate=null_rate,
            unique_count=unique_count,
            sample_values=samples,
            min_value=min_val,
            max_value=max_val,
        )

    logger.info(f"profile_records: profiled {len(profiles)} fields from {total} records")
    return profiles


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _flatten(
    obj: dict[str, Any],
    prefix: str = "",
    sep: str = ".",
) -> dict[str, Any]:
    """Recursively flatten a nested dict to dot-notation keys.

    Lists with dict elements: only the first element's structure is used
    (schema inference, not data unrolling).
    """
    result: dict[str, Any] = {}
    for k, v in obj.items():
        full_key = f"{prefix}{sep}{k}" if prefix else k
        if isinstance(v, dict):
            result.update(_flatten(v, full_key, sep))
        elif isinstance(v, list) and v and isinstance(v[0], dict):
            # Flatten first element to capture schema; mark as list in key
            result.update(_flatten(v[0], full_key, sep))
        else:
            result[full_key] = v
    return result


def _hashable(value: Any) -> Any:
    """Convert a value to something hashable for use in a set."""
    if isinstance(value, dict):
        return tuple(sorted(value.items()))
    if isinstance(value, list):
        return tuple(value)
    return value


def _infer_postgres_type(values: list[Any], field_name: str) -> str:
    """Infer a Postgres type from a sample of non-null values.

    Rules (deterministic, no LLM):
    1. Field name heuristic for timestamptz (ends with _at, _time, _date)
    2. All bool -> boolean
    3. All int (and not bool) -> integer
    4. All float, or mix of int+float -> real
    5. All str -> text (with timestamptz heuristic on name)
    6. dict or list -> jsonb
    7. Mixed -> jsonb (safe fallback)
    """
    if not values:
        return "text"

    # Name-based heuristic for timestamps
    lower_name = field_name.lower()
    if any(lower_name.endswith(s) for s in ("_at", "_time", "_date", "time", "date")):
        if all(isinstance(v, str) for v in values):
            return "timestamptz"

    # Type inspection
    types = {type(v) for v in values}

    if types == {bool}:
        return "boolean"

    # int check — bool is subclass of int, exclude explicitly
    if types <= {int} and bool not in types:
        return "integer"

    if types <= {float}:
        return "real"

    if types <= {int, float} and bool not in types:
        return "real"

    if types <= {str}:
        return "text"

    if any(isinstance(v, (dict, list)) for v in values):
        return "jsonb"

    # Mixed scalar fallback
    return "jsonb"
