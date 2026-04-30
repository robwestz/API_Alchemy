"""CLI: python -m alchemy ingest <url>"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from typing import Any
from uuid import UUID, uuid4

from loguru import logger


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alchemy",
        description="API Alchemy Engine CLI — Fas 2 ingest path",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    ingest_cmd = sub.add_parser(
        "ingest",
        help="Ingest a URL, profile the data and print inferred Postgres schema",
    )
    ingest_cmd.add_argument(
        "url",
        type=str,
        help="API URL to ingest (Fas 2: only open-meteo URLs supported)",
    )
    ingest_cmd.add_argument(
        "--project-id",
        type=str,
        default=None,
        help="Project UUID to associate records with (default: generate new UUID)",
    )
    ingest_cmd.add_argument(
        "--max-records",
        type=int,
        default=100,
        help="Maximum number of records to sample (default: 100)",
    )
    return parser


async def _run_ingest(url: str, project_id: UUID, max_records: int) -> None:
    """Core ingest pipeline: fetch -> profile -> infer_schema -> print."""
    # Lazy imports keep startup fast and allow graceful dep-error messages
    try:
        from packages.adapters.open_meteo import OpenMeteoAdapter  # noqa: PLC0415
    except ImportError as exc:
        logger.error(f"Cannot import OpenMeteoAdapter: {exc}")
        sys.exit(1)

    try:
        from packages.parser.profile import profile_records  # noqa: PLC0415
    except ImportError as exc:
        logger.error(f"Cannot import profile_records: {exc}")
        sys.exit(1)

    try:
        from packages.lake.schema_inference import infer_schema  # noqa: PLC0415
    except ImportError as exc:
        logger.error(f"Cannot import infer_schema: {exc}")
        sys.exit(1)

    # Validate URL — Fas 2 only supports open-meteo
    if "open-meteo" not in url:
        logger.error(
            "Fas 2 only supports open-meteo URLs. "
            f"Received: {url!r}. "
            "Hint: try https://api.open-meteo.com/v1/forecast"
            "?latitude=59.33&longitude=18.07"
            "&current=temperature_2m,relative_humidity_2m,wind_speed_10m"
        )
        sys.exit(1)

    logger.info(f"Ingesting URL: {url}")
    logger.info(f"Project ID: {project_id}")

    # Parse query params from URL to pass as adapter query dict
    query = _parse_query_from_url(url)

    adapter = OpenMeteoAdapter(project_id=project_id)
    records: list[Any] = []

    logger.info("Fetching records from open-meteo…")
    async for record in adapter.fetch(query):
        records.append(record)
        if len(records) >= max_records:
            logger.info(f"Reached max_records limit ({max_records}), stopping fetch")
            break

    if not records:
        logger.warning("No records returned from adapter")
        sys.exit(0)

    logger.info(f"Fetched {len(records)} record(s)")

    # Profile fields deterministically — no LLM calls
    logger.info("Profiling records…")
    profiles = profile_records(records)
    logger.info(f"Profiled {len(profiles)} field(s): {list(profiles.keys())}")

    # Infer Postgres schema — no LLM calls
    logger.info("Inferring Postgres schema…")
    sql = infer_schema("open_meteo", profiles)

    logger.info("=== Inferred Postgres Schema ===")
    print(sql)
    logger.info("=== End Schema ===")

    # Optional: write records to Lake if DATABASE_URL is set
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        logger.warning(
            "DATABASE_URL not set — skipping Lake write. "
            "Set DATABASE_URL=postgres://... to persist records."
        )
    else:
        await _write_to_lake(database_url, records)


async def _write_to_lake(database_url: str, records: list[Any]) -> None:
    """Write records to Lake. Only called when DATABASE_URL is set."""
    try:
        from packages.lake.repository import LakeRepository  # noqa: PLC0415
    except ImportError as exc:
        logger.warning(f"Cannot import LakeRepository: {exc} — skipping Lake write")
        return

    repo = LakeRepository()
    try:
        await repo.connect(dsn=database_url)
        import json  # noqa: PLC0415

        for record in records:
            await repo.execute(
                """
                INSERT INTO records
                    (project_id, adapter_name, adapter_version,
                     schema_hash, payload, fetched_at, lineage)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7::jsonb)
                """,
                record.project_id,
                record.adapter_name,
                record.adapter_version,
                record.schema_hash,
                json.dumps(record.payload),
                record.fetched_at,
                json.dumps(record.lineage),
            )
        logger.info(f"Wrote {len(records)} record(s) to Lake")
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Failed to write records to Lake: {exc}")
    finally:
        await repo.close()


def _parse_query_from_url(url: str) -> dict[str, str]:
    """Extract query parameters from a URL string.

    Returns a dict of param_name -> value (first value when repeated).
    The adapter handles defaults, so an empty dict is valid.
    """
    from urllib.parse import parse_qs, urlparse  # noqa: PLC0415

    parsed = urlparse(url)
    raw_qs = parse_qs(parsed.query, keep_blank_values=True)
    return {k: v[0] for k, v in raw_qs.items() if v}


def main() -> None:
    """Entry-point registered in pyproject.toml [project.scripts]."""
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "ingest":
        project_id: UUID = UUID(args.project_id) if args.project_id else uuid4()
        asyncio.run(
            _run_ingest(
                url=args.url,
                project_id=project_id,
                max_records=args.max_records,
            )
        )
    else:
        parser.print_help()
        sys.exit(1)
