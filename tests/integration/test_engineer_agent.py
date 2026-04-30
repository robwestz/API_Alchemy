"""Integration tests for EngineerAgent.

Mocks LLM and httpx to verify the agent loop without real network or API calls.
Tests cover: success path, retry logic, cost-cap, sandbox-failure handling.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from packages.agents.engineer.agent import (
    AdapterDraft,
    EndpointSpec,
    EngineerAgent,
    MAX_COST_PER_GENERATION_USD,
)
from packages.interfaces import SandboxResult


_DEMO_DRAFT = AdapterDraft(
    api_name="demo_api",
    base_url="https://api.example.com",
    endpoints=[
        EndpointSpec(
            path="/v1/items",
            method="GET",
            query_params=["limit"],
            response_fields={"id": "str", "value": "int"},
            requires_auth=False,
            auth_header=None,
        )
    ],
    secrets_required=[],
    rate_limit_hint=None,
    doc_url="https://example.com/docs",
    llm_confidence=0.9,
)


def _green_sandbox() -> MagicMock:
    sandbox = MagicMock()
    sandbox.run = AsyncMock(
        return_value=SandboxResult(
            success=True,
            stdout="OK",
            stderr="",
            exit_code=0,
            duration_ms=100,
            network_calls=[],
        )
    )
    return sandbox


def _red_sandbox() -> MagicMock:
    sandbox = MagicMock()
    sandbox.run = AsyncMock(
        return_value=SandboxResult(
            success=False,
            stdout="",
            stderr="ImportError: missing dep",
            exit_code=1,
            duration_ms=50,
            network_calls=[],
        )
    )
    return sandbox


def _mock_llm_returning_draft(draft: AdapterDraft = _DEMO_DRAFT) -> AsyncMock:
    return AsyncMock(return_value=draft)


def _mock_httpx_doc(content: str = "<html>API docs</html>") -> Any:
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.text = content
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_resp)
    return mock_client


@pytest.mark.integration
@pytest.mark.asyncio
async def test_engineer_agent_happy_path() -> None:
    sandbox = _green_sandbox()
    llm = _mock_llm_returning_draft()

    with tempfile.TemporaryDirectory() as tmp:
        agent = EngineerAgent(
            sandbox=sandbox,
            llm_complete=llm,
            generated_root=Path(tmp),
        )

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value = _mock_httpx_doc()
            result = await agent.loop(
                {"doc_url": "https://example.com/docs", "project_id": uuid4()}
            )

        assert result.success is True
        assert result.agent_name == "engineer"
        assert "read_doc" in result.tool_calls_made
        assert "write_pydantic_model" in result.tool_calls_made
        assert "write_adapter" in result.tool_calls_made
        assert "sandbox_test" in result.tool_calls_made
        assert "register_adapter" in result.tool_calls_made
        assert result.output["manual_approval_required"] is True

        target_dir = Path(tmp) / "demo_api" / "v1"
        assert (target_dir / "model.py").exists()
        assert (target_dir / "demo_api_adapter.py").exists()
        assert (target_dir / "sandbox_test.py").exists()
        assert (target_dir / "manifest.json").exists()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_engineer_agent_missing_input() -> None:
    sandbox = _green_sandbox()
    llm = _mock_llm_returning_draft()
    agent = EngineerAgent(sandbox=sandbox, llm_complete=llm)

    result = await agent.loop({"doc_url": "", "project_id": uuid4()})
    assert result.success is False
    assert "missing" in result.output["error"]
    llm.assert_not_called()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_engineer_agent_doc_fetch_failure() -> None:
    sandbox = _green_sandbox()
    llm = _mock_llm_returning_draft()
    agent = EngineerAgent(sandbox=sandbox, llm_complete=llm)

    failing_client = AsyncMock()
    failing_client.__aenter__ = AsyncMock(return_value=failing_client)
    failing_client.__aexit__ = AsyncMock(return_value=None)
    failing_client.get = AsyncMock(side_effect=RuntimeError("network error"))

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value = failing_client
        result = await agent.loop(
            {"doc_url": "https://example.com/docs", "project_id": uuid4()}
        )

    assert result.success is False
    assert "doc-fetch failed" in result.output["error"]
    llm.assert_not_called()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_engineer_agent_llm_retries_then_failure() -> None:
    sandbox = _green_sandbox()
    llm = AsyncMock(side_effect=RuntimeError("rate limit"))
    agent = EngineerAgent(sandbox=sandbox, llm_complete=llm)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value = _mock_httpx_doc()
        result = await agent.loop(
            {"doc_url": "https://example.com/docs", "project_id": uuid4()}
        )

    assert result.success is False
    assert "LLM extraction failed" in result.output["error"]
    assert llm.call_count == 3


@pytest.mark.integration
@pytest.mark.asyncio
async def test_engineer_agent_sandbox_failure() -> None:
    sandbox = _red_sandbox()
    llm = _mock_llm_returning_draft()

    with tempfile.TemporaryDirectory() as tmp:
        agent = EngineerAgent(
            sandbox=sandbox,
            llm_complete=llm,
            generated_root=Path(tmp),
        )

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value = _mock_httpx_doc()
            result = await agent.loop(
                {"doc_url": "https://example.com/docs", "project_id": uuid4()}
            )

        assert result.success is False
        assert "sandbox validation failed" in result.output["error"]
        assert (Path(tmp) / "demo_api" / "v1" / "demo_api_adapter.py").exists()
        assert sandbox.run.call_count == 3


@pytest.mark.integration
@pytest.mark.asyncio
async def test_engineer_agent_cost_recorded() -> None:
    sandbox = _green_sandbox()
    expensive_result = MagicMock()
    expensive_result.cost_usd = MAX_COST_PER_GENERATION_USD + 1.0
    expensive_result.content = (
        '{"api_name":"demo_api","base_url":"https://api.example.com",'
        '"endpoints":[{"path":"/v1/items","method":"GET","query_params":[],'
        '"response_fields":{},"requires_auth":false,"auth_header":null}],'
        '"secrets_required":[],"rate_limit_hint":null,'
        '"doc_url":"https://example.com/docs","llm_confidence":0.9}'
    )
    expensive_result.structured = _DEMO_DRAFT

    llm = AsyncMock(return_value=expensive_result)

    with tempfile.TemporaryDirectory() as tmp:
        agent = EngineerAgent(
            sandbox=sandbox,
            llm_complete=llm,
            generated_root=Path(tmp),
        )

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value = _mock_httpx_doc()
            result = await agent.loop(
                {"doc_url": "https://example.com/docs", "project_id": uuid4()}
            )

    assert result.cost_usd >= MAX_COST_PER_GENERATION_USD
