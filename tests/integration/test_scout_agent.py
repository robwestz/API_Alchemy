"""Integration tests for ScoutAgent.

Mocks LLM and web_search/fetch to verify the agent loop without real network.
Tests cover: happy path, missing input, retry, cost-cap, web_search integration.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from packages.agents.scout.agent import (
    MAX_COST_PER_DISCOVERY_USD,
    ScoutAgent,
)
from packages.interfaces import DiscoveryCandidate, DiscoveryReport


def _demo_report(
    project_id_str: str = "00000000-0000-0000-0000-000000000001",
) -> DiscoveryReport:
    return DiscoveryReport(
        project_id=UUID(project_id_str),
        domain="fintech i Sverige",
        candidates=[
            DiscoveryCandidate(
                api_name="Swish Payments API",
                doc_url="https://developer.swish.nu/api",
                estimated_cost_per_1k=0.0,
                data_coverage="Mobile payments in Sweden",
                reliability_score=0.85,
                requires_secret=True,
            ),
            DiscoveryCandidate(
                api_name="Klarna API",
                doc_url="https://developers.klarna.com/api/",
                estimated_cost_per_1k=0.0,
                data_coverage="Payments and BNPL",
                reliability_score=0.9,
                requires_secret=True,
            ),
            DiscoveryCandidate(
                api_name="Riksbank Open Data",
                doc_url="https://www.riksbank.se/api",
                estimated_cost_per_1k=0.0,
                data_coverage="Interest rates, exchange rates",
                reliability_score=0.95,
                requires_secret=False,
            ),
            DiscoveryCandidate(
                api_name="Fortnox API",
                doc_url="https://developer.fortnox.se/documentation/",
                estimated_cost_per_1k=0.0,
                data_coverage="Accounting, invoicing",
                reliability_score=0.8,
                requires_secret=True,
            ),
            DiscoveryCandidate(
                api_name="Bolagsverket Naringslivsregistret",
                doc_url="https://bolagsverket.se/api",
                estimated_cost_per_1k=0.0,
                data_coverage="Swedish company registry",
                reliability_score=0.7,
                requires_secret=False,
            ),
        ],
        cost_usd=0.0,
        generated_at=datetime.now(tz=timezone.utc),
    )


def _mock_llm_returning_report(report: DiscoveryReport | None = None) -> AsyncMock:
    return AsyncMock(return_value=report or _demo_report())


@pytest.mark.integration
@pytest.mark.asyncio
async def test_scout_happy_path() -> None:
    project_id = uuid4()
    llm = _mock_llm_returning_report(_demo_report(str(project_id)))
    agent = ScoutAgent(llm_complete=llm)

    result = await agent.loop(
        {"domain": "fintech i Sverige", "project_id": project_id, "max_candidates": 5}
    )

    assert result.success is True
    assert result.agent_name == "scout"
    assert "evaluate_api" in result.tool_calls_made
    assert result.output["candidate_count"] == 5
    candidates = result.output["discovery_report"]["candidates"]
    assert len(candidates) == 5
    for cand in candidates:
        assert "api_name" in cand
        assert "doc_url" in cand
        assert "reliability_score" in cand


@pytest.mark.integration
@pytest.mark.asyncio
async def test_scout_missing_domain() -> None:
    llm = _mock_llm_returning_report()
    agent = ScoutAgent(llm_complete=llm)

    result = await agent.loop({"project_id": uuid4()})
    assert result.success is False
    assert "missing" in result.output["error"]
    llm.assert_not_called()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_scout_llm_retries_then_failure() -> None:
    llm = AsyncMock(side_effect=RuntimeError("rate limit"))
    agent = ScoutAgent(llm_complete=llm)

    result = await agent.loop({"domain": "test", "project_id": uuid4()})
    assert result.success is False
    assert "LLM extraction failed" in result.output["error"]
    assert llm.call_count == 3


@pytest.mark.integration
@pytest.mark.asyncio
async def test_scout_cost_cap_recorded() -> None:
    expensive_result = MagicMock()
    expensive_result.cost_usd = MAX_COST_PER_DISCOVERY_USD + 0.5
    expensive_result.structured = _demo_report()

    llm = AsyncMock(return_value=expensive_result)
    agent = ScoutAgent(llm_complete=llm)

    result = await agent.loop({"domain": "test", "project_id": uuid4()})
    assert result.cost_usd >= MAX_COST_PER_DISCOVERY_USD


@pytest.mark.integration
@pytest.mark.asyncio
async def test_scout_with_web_search_mock() -> None:
    project_id = uuid4()
    llm = _mock_llm_returning_report(_demo_report(str(project_id)))

    web_search = AsyncMock(
        return_value=[
            {
                "title": "Swish API",
                "url": "https://developer.swish.nu/api",
                "snippet": "Mobile payments",
            },
            {
                "title": "Klarna Docs",
                "url": "https://developers.klarna.com/",
                "snippet": "BNPL platform",
            },
        ]
    )
    web_fetch = AsyncMock(return_value="<html>Mocked doc content</html>")

    agent = ScoutAgent(
        llm_complete=llm,
        web_search_fn=web_search,
        web_fetch_fn=web_fetch,
    )

    result = await agent.loop({"domain": "fintech i Sverige", "project_id": project_id})

    assert result.success is True
    assert "web_search" in result.tool_calls_made
    assert "web_fetch" in result.tool_calls_made
    assert result.output["search_results_used"] == 2

    llm_call_args = llm.call_args
    messages = llm_call_args.kwargs["messages"]
    user_content = messages[1]["content"]
    assert "Swish API" in user_content
    assert "Klarna Docs" in user_content
