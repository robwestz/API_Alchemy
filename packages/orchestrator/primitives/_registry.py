"""Tool Registry — single source of truth for action parity.

Exporterar `TOOL_REGISTRY: ToolRegistry` med registrerade primitives.
Varje primitive har Pydantic in/out-modeller och en async handler.

Per ARCHITECTURE.md sektion 4 och DECISIONS.md D6:
  - Inga API-specifika if-satser
  - Importeras av Gateway (/api/tools) och CI-test (test_action_parity.py)
  - UI-konsumtion hör till Fas 6
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from packages.interfaces import ToolRegistry, ToolSpec


# ---------------------------------------------------------------------------
# Primitives: health_check
# ---------------------------------------------------------------------------


class HealthCheckInput(BaseModel):
    """Input till health_check — inga parametrar krävs."""

    pass


class HealthCheckOutput(BaseModel):
    """Output från health_check."""

    status: str = Field(description="Alltid 'ok' om systemet är up")
    ts: str = Field(description="ISO 8601 timestamp (UTC)")


async def _health_check_handler(inp: HealthCheckInput) -> HealthCheckOutput:
    """Returnerar systemstatus och aktuell timestamp."""
    return HealthCheckOutput(
        status="ok",
        ts=datetime.now(tz=timezone.utc).isoformat(),
    )


_health_check_spec: ToolSpec[HealthCheckInput, HealthCheckOutput] = ToolSpec(
    name="health_check",
    description=(
        "Returnerar systemstatus och aktuell server-tid. "
        "Används av Gateway /health och som smoke-test."
    ),
    input_schema=HealthCheckInput,
    output_schema=HealthCheckOutput,
    handler=_health_check_handler,
    agent_allowed=True,
    ui_visible=True,
    ui_component="StatusBadge",
)


# ---------------------------------------------------------------------------
# Registry — lägg till fler primitives här i Fas 1+
# ---------------------------------------------------------------------------

TOOL_REGISTRY: ToolRegistry = {
    "health_check": _health_check_spec,
}

__all__ = [
    "TOOL_REGISTRY",
    "HealthCheckInput",
    "HealthCheckOutput",
]
