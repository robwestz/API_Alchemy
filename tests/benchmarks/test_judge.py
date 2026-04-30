"""Benchmark tests for JudgeAgent and leaderboard ranking (Fas 5).

All tests use mocks -- no real network calls, no real LLM calls.
Per PHASE_PLAN.md Fas 5 DoD: pytest tests/benchmarks/test_judge.py must be green.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from packages.agents.judge.agent import JudgeAgent
from packages.agents.judge.leaderboard import compute_ranking
from packages.interfaces import (
    AdapterManifest,
    ArenaScore,
    BaseAdapter,
    Record,
    SecretsResolver,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_record(payload: dict[str, Any], adapter_name: str = "mock_adapter") -> Record:
    return Record(
        project_id=uuid4(),
        adapter_name=adapter_name,
        adapter_version="1.0.0",
        schema_hash="abc123",
        payload=payload,
        fetched_at=datetime.now(tz=timezone.utc),
    )


def _make_arena_score(
    name: str,
    latency_p50_ms: float = 100.0,
    fields_per_response: int = 10,
    cost_per_1k_usd: float = 0.0,
    dx_score: float = 0.7,
) -> ArenaScore:
    return ArenaScore(
        adapter_name=name,
        adapter_version="1.0.0",
        latency_p50_ms=latency_p50_ms,
        latency_p95_ms=latency_p50_ms * 1.5,
        fields_per_response=fields_per_response,
        cost_per_1k_usd=cost_per_1k_usd,
        dx_score=dx_score,
        measured_at=datetime.now(tz=timezone.utc),
    )


class _MockAdapter(BaseAdapter):
    """Deterministic mock adapter for benchmark tests. No network calls."""

    name: str = "mock_adapter"
    version: str = "1.0.0"
    schema_hash: str = "deadbeef"
    secrets_required: list[str] = []

    def __init__(self, payload: dict[str, Any] | None = None) -> None:
        self._payload: dict[str, Any] = payload or {
            "temperature": 12.5,
            "humidity": 71,
            "wind_speed": 4.2,
            "latitude": 59.33,
            "longitude": 18.07,
        }

    def fetch(
        self,
        query: dict[str, Any],
        secrets: SecretsResolver | None = None,
    ) -> AsyncIterator[Record]:
        return self._gen()

    async def _gen(self) -> AsyncIterator[Record]:  # type: ignore[override]
        yield _make_record(self._payload)

    def manifest(self) -> AdapterManifest:
        return AdapterManifest(
            name=self.name,
            version=self.version,
            schema_hash=self.schema_hash,
            doc_url="https://example.com/docs",
            generated_at=datetime.now(tz=timezone.utc),
            model_used="mock",
            prompts_used=[],
        )


def _mock_llm_dx(dx_score: float) -> AsyncMock:
    """Return an async mock LLM that yields a JSON DX-score response string."""
    payload = json.dumps({"dx_score": dx_score, "rationale": "mock rationale"})
    return AsyncMock(return_value=payload)


# ---------------------------------------------------------------------------
# Test 1: happy path
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_judge_happy_path() -> None:
    """Mock adapter + mock LLM (DX=0.85) -> success=True with all ArenaScore fields."""
    adapter = _MockAdapter()
    llm = _mock_llm_dx(0.85)
    agent = JudgeAgent(adapter=adapter, llm_complete=llm)

    result = await agent.loop({"project_id": str(uuid4())})

    assert result.success is True
    assert result.agent_name == "judge"

    arena = result.output["arena_score"]
    assert "latency_p50_ms" in arena
    assert "latency_p95_ms" in arena
    assert "fields_per_response" in arena
    assert "cost_per_1k_usd" in arena
    assert "dx_score" in arena

    assert isinstance(arena["latency_p50_ms"], float)
    assert arena["latency_p50_ms"] >= 0.0
    assert isinstance(arena["fields_per_response"], int)
    assert arena["fields_per_response"] > 0
    assert 0.0 <= arena["dx_score"] <= 1.0

    assert "run_benchmark" in result.tool_calls_made
    assert "score_api" in result.tool_calls_made
    assert "update_leaderboard" in result.tool_calls_made


# ---------------------------------------------------------------------------
# Test 2: missing adapter -> failure
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_judge_missing_adapter() -> None:
    """JudgeAgent without an adapter must return success=False immediately."""
    agent = JudgeAgent(adapter=None)

    result = await agent.loop({"project_id": str(uuid4())})

    assert result.success is False
    assert "error" in result.output
    assert "adapter" in result.output["error"].lower()


# ---------------------------------------------------------------------------
# Test 3: leaderboard default weights
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_leaderboard_default_weights() -> None:
    """compute_ranking with default weights: best-all-round adapter ranks first."""
    best_all = _make_arena_score(
        "best_all",
        latency_p50_ms=50.0,
        fields_per_response=15,
        cost_per_1k_usd=0.0,
        dx_score=0.9,
    )
    middle = _make_arena_score(
        "middle",
        latency_p50_ms=200.0,
        fields_per_response=10,
        cost_per_1k_usd=0.5,
        dx_score=0.6,
    )
    worst = _make_arena_score(
        "worst",
        latency_p50_ms=800.0,
        fields_per_response=3,
        cost_per_1k_usd=2.0,
        dx_score=0.2,
    )

    ranking = compute_ranking([best_all, middle, worst])

    assert len(ranking) == 3
    names = [r[0] for r in ranking]
    scores = [r[1] for r in ranking]

    # Scores must be non-ascending
    assert scores[0] >= scores[1] >= scores[2]
    # best_all dominates on latency, cost, and dx -> must rank first
    assert names[0] == "best_all"
    # worst is bad on every dimension -> must rank last
    assert names[-1] == "worst"


# ---------------------------------------------------------------------------
# Test 4: leaderboard custom weights (latency only)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_leaderboard_custom_weights() -> None:
    """With latency weight=1.0 and all others=0, lowest-latency adapter ranks first."""
    fast = _make_arena_score(
        "fast",
        latency_p50_ms=30.0,
        fields_per_response=2,
        cost_per_1k_usd=5.0,
        dx_score=0.1,
    )
    rich_fields = _make_arena_score(
        "rich_fields",
        latency_p50_ms=500.0,
        fields_per_response=50,
        cost_per_1k_usd=0.0,
        dx_score=0.95,
    )
    medium = _make_arena_score(
        "medium",
        latency_p50_ms=200.0,
        fields_per_response=20,
        cost_per_1k_usd=1.0,
        dx_score=0.5,
    )

    ranking = compute_ranking(
        [fast, rich_fields, medium],
        weights={"latency": 1.0, "fields": 0.0, "cost": 0.0, "dx": 0.0},
    )

    assert len(ranking) == 3
    # Only latency matters -> lowest latency (fast) must be first
    assert ranking[0][0] == "fast"
    # Highest latency (rich_fields) must be last
    assert ranking[-1][0] == "rich_fields"


# ---------------------------------------------------------------------------
# Test 5: leaderboard deterministic
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_leaderboard_deterministic() -> None:
    """Running compute_ranking 3 times with the same input yields identical output."""
    scores = [
        _make_arena_score("alpha", latency_p50_ms=100.0, dx_score=0.8),
        _make_arena_score("beta", latency_p50_ms=200.0, dx_score=0.6),
        _make_arena_score("gamma", latency_p50_ms=150.0, dx_score=0.7),
    ]

    result_1 = compute_ranking(scores)
    result_2 = compute_ranking(scores)
    result_3 = compute_ranking(scores)

    assert result_1 == result_2, "Second run differs from first"
    assert result_2 == result_3, "Third run differs from second"


# ---------------------------------------------------------------------------
# Test 6: DX score clamping / bounding
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_judge_dx_score_bounded() -> None:
    """When LLM returns dx_score > 1.0, JudgeAgent must clamp it to <= 1.0.

    A valid score (0.5) must pass through unchanged.
    """
    adapter = _MockAdapter()

    # Case A: LLM returns 1.5 (out of bounds above) -> must be clamped to 1.0
    llm_over = _mock_llm_dx(1.5)
    agent_over = JudgeAgent(adapter=adapter, llm_complete=llm_over)
    result_over = await agent_over.loop({"project_id": str(uuid4())})

    assert result_over.success is True
    clamped = result_over.output["arena_score"]["dx_score"]
    assert clamped <= 1.0, f"Expected dx_score clamped to <=1.0, got {clamped}"
    assert clamped == pytest.approx(1.0, abs=1e-9)

    # Case B: LLM returns 0.5 (valid) -> must pass through unchanged
    llm_ok = _mock_llm_dx(0.5)
    agent_ok = JudgeAgent(adapter=adapter, llm_complete=llm_ok)
    result_ok = await agent_ok.loop({"project_id": str(uuid4())})

    assert result_ok.success is True
    ok_score = result_ok.output["arena_score"]["dx_score"]
    assert ok_score == pytest.approx(0.5, abs=1e-6)
