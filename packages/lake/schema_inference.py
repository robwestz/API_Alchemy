"""Schema inference — Records -> Postgres CREATE TABLE statement.

Deterministisk, inga LLM-anrop. Tar FieldProfile-dict (fran parser.profile)
och producerar ett giltig CREATE TABLE IF NOT EXISTS SQL-statement.

Per ARCHITECTURE.md sektion 1: Lake records har JSONB payload.
schema_inference producerar ett *flattened* adapter-specifikt schema
for analys- och BI-anvandning, parallellt med den generiska records-tabellen.
"""

from __future__ import annotations

import re

from loguru import logger

from packages.parser.profile import FieldProfile

__all__ = ["infer_schema"]

# Standard columns present in every inferred adapter table
_STANDARD_COLUMNS: list[tuple[str, str]] = [
    ("id", "BIGSERIAL PRIMARY KEY"),
    ("project_id", "UUID NOT NULL REFERENCES projects(id)"),
    ("fetched_at", "TIMESTAMPTZ NOT NULL"),
    ("adapter_version", "TEXT NOT NULL"),
    ("schema_hash", "TEXT NOT NULL"),
]

# Mapping from FieldProfile.inferred_type -> Postgres DDL type
_TYPE_MAP: dict[str, str] = {
    "text": "TEXT",
    "integer": "INTEGER",
    "real": "REAL",
    "boolean": "BOOLEAN",
    "jsonb": "JSONB",
    "timestamptz": "TIMESTAMPTZ",
}


def infer_schema(
    adapter_name: str,
    profiles: dict[str, FieldProfile],
) -> str:
    """Return a CREATE TABLE IF NOT EXISTS SQL statement for the given adapter.

    Table name: `<adapter_name>_records`
    Standard columns are always included first.
    One column is added per FieldProfile entry.
    Dot-notation field names are sanitised to valid SQL identifiers
    (dots replaced with underscores).

    No LLM calls — purely deterministic.
    """
    table_name = f"{_sanitise_identifier(adapter_name)}_records"
    logger.info(
        f"infer_schema: building CREATE TABLE for {table_name!r} "
        f"from {len(profiles)} profile(s)"
    )

    column_lines: list[str] = []

    # 1. Standard columns
    for col_name, col_def in _STANDARD_COLUMNS:
        column_lines.append(f"    {col_name} {col_def}")

    # 2. Adapter-specific columns derived from profiles
    # Skip fields that clash with standard column names
    standard_names = {col for col, _ in _STANDARD_COLUMNS}

    for field_name, profile in sorted(profiles.items()):
        safe_name = _sanitise_identifier(field_name)
        if safe_name in standard_names:
            logger.debug(
                f"infer_schema: skipping field {field_name!r} "
                f"— clashes with standard column {safe_name!r}"
            )
            continue

        pg_type = _TYPE_MAP.get(profile.inferred_type, "TEXT")
        # All adapter-specific columns are nullable (API may omit fields)
        column_lines.append(f"    {safe_name} {pg_type}")

    columns_sql = ",\n".join(column_lines)
    sql = (
        f"CREATE TABLE IF NOT EXISTS {table_name} (\n"
        f"{columns_sql}\n"
        f");"
    )

    logger.debug(f"infer_schema: generated SQL ({len(sql)} chars)")
    return sql


def _sanitise_identifier(name: str) -> str:
    """Convert an arbitrary string to a safe Postgres identifier.

    - Lowercase
    - Dots, spaces, hyphens -> underscore
    - Strip leading digits by prefixing with underscore
    - Truncate to 63 characters (Postgres identifier limit)
    """
    safe = name.lower()
    for ch in (".", " ", "-"):
        safe = safe.replace(ch, "_")
    # Replace any remaining non-alphanumeric/underscore chars
    safe = re.sub(r"[^a-z0-9_]", "_", safe)
    if safe and safe[0].isdigit():
        safe = f"_{safe}"
    return safe[:63]
