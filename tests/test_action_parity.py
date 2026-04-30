"""Action parity CI-test.

Verifierar att TOOL_REGISTRY ar konsistent och att varje registrerad
ToolSpec uppfyller kontraktet. Kraver INGEN DB - kor alltid i CI.

Per ARCHITECTURE.md sektion 4 och DECISIONS.md D6.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from packages.orchestrator.primitives._registry import TOOL_REGISTRY


def test_registry_imports_without_error() -> None:
    """TOOL_REGISTRY importerar utan exception."""
    assert TOOL_REGISTRY is not None


def test_health_check_registered() -> None:
    """health_check maste finnas i TOOL_REGISTRY."""
    assert "health_check" in TOOL_REGISTRY, (
        "health_check saknas i TOOL_REGISTRY - "
        "minst en primitive maste vara registrerad (D6)"
    )


def test_all_tool_names_unique() -> None:
    """Inga namnkollisioner - dict-nycklar ar unika per definition,
    men vi verifierar aven att spec.name matchar nyckeln."""
    for key, spec in TOOL_REGISTRY.items():
        assert spec.name == key, (
            f"ToolSpec.name={spec.name!r} matchar inte registry-nyckeln {key!r}"
        )


def test_all_tools_have_valid_input_schema() -> None:
    """Varje ToolSpec.input_schema maste vara en subklass av BaseModel."""
    for name, spec in TOOL_REGISTRY.items():
        assert isinstance(spec.input_schema, type), (
            f"Tool {name!r}: input_schema ar inte en klass"
        )
        assert issubclass(spec.input_schema, BaseModel), (
            f"Tool {name!r}: input_schema {spec.input_schema!r} "
            "ar inte en subklass av BaseModel"
        )


def test_all_tools_have_valid_output_schema() -> None:
    """Varje ToolSpec.output_schema maste vara en subklass av BaseModel."""
    for name, spec in TOOL_REGISTRY.items():
        assert isinstance(spec.output_schema, type), (
            f"Tool {name!r}: output_schema ar inte en klass"
        )
        assert issubclass(spec.output_schema, BaseModel), (
            f"Tool {name!r}: output_schema {spec.output_schema!r} "
            "ar inte en subklass av BaseModel"
        )


def test_all_tools_have_handler() -> None:
    """Varje ToolSpec maste ha en callable handler."""
    for name, spec in TOOL_REGISTRY.items():
        assert callable(spec.handler), (
            f"Tool {name!r}: handler ar inte callable"
        )


def test_all_tools_have_description() -> None:
    """Varje ToolSpec maste ha en icke-tom description."""
    for name, spec in TOOL_REGISTRY.items():
        assert spec.description and spec.description.strip(), (
            f"Tool {name!r}: description ar tom"
        )


def test_health_check_schema_serializable() -> None:
    """health_check input/output-schema maste vara JSON-serialiserbara."""
    spec = TOOL_REGISTRY["health_check"]
    input_schema = spec.input_schema.model_json_schema()
    output_schema = spec.output_schema.model_json_schema()
    assert isinstance(input_schema, dict)
    assert isinstance(output_schema, dict)
    props = output_schema.get("properties", {})
    assert "status" in props, "health_check output_schema saknar 'status'-falt"
    assert "ts" in props, "health_check output_schema saknar 'ts'-falt"


@pytest.mark.asyncio
async def test_health_check_handler_returns_ok() -> None:
    """health_check handler maste returnera status='ok' och ett ts-falt."""
    spec = TOOL_REGISTRY["health_check"]
    inp = spec.input_schema()
    result = await spec.handler(inp)
    assert result.status == "ok"  # type: ignore[union-attr]
    assert result.ts  # type: ignore[union-attr]
    assert "T" in result.ts  # type: ignore[union-attr]
