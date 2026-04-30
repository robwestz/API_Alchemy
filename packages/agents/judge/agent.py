"""JudgeAgent -- Arena benchmark and DX scoring (Fas 5 skeleton).

Workflow:
1. Validate adapter is present
2. Run BENCHMARK_RUNS fetches against adapter, measure per-fetch latency
3. Compute p50, p95 (numpy if available; fallback to manual sort)
4. Count fields per response (max over all runs)
5. Estimate cost_per_1k from adapter config (free -> 0.0)
6. LLM call for DX-score with sample response + latency
7. Produce ArenaScore Pydantic object
8. Return AgentResult(success=True, output={"arena_score": score.model_dump(mode="json")})

Per ARCHITECTURE.md sektion 3 Loop 3 (self-evaluating).
No LLM calls outside litellm_wrapper.complete(). No DB writes in Fas 5 skeleton.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from loguru import logger

from packages.agents.judge.prompts import (
    DX_EXAMPLES,
    DX_SYSTEM_PROMPT,
    build_dx_prompt,
)
from packages.interfaces import (
    AgentResult,
    ArenaScore,
    BaseAdapter,
    BaseAgent,
    Role,
)

__all__ = ["JudgeAgent"]

MAX_COST_PER_BENCHMARK_USD: float = 1.0
BENCHMARK_RUNS: int = 10
BENCHMARK_TIMEOUT_S: float = 30.0

_DEFAULT_QUERY: dict[str, str] = {
    "latitude": "59.33",
    "longitude": "18.07",
    "current": "temperature_2m,relative_humidity_2m,wind_speed_10m",
}


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Return the pct-th percentile from a pre-sorted list (0 < pct <= 100)."""
    if not sorted_values:
        return 0.0
    index = (pct / 100.0) * (len(sorted_values) - 1)
    lower = int(index)
    upper = min(lower + 1, len(sorted_values) - 1)
    frac = index - lower
    return sorted_values[lower] * (1.0 - frac) + sorted_values[upper] * frac


def _compute_p50_p95(latencies_ms: list[float]) -> tuple[float, float]:
    """Compute p50 and p95 latency. Uses numpy if available, else pure Python."""
    if not latencies_ms:
        return 0.0, 0.0
    try:
        import numpy as np  # noqa: PLC0415

        arr = np.array(latencies_ms, dtype=float)
        return float(np.percentile(arr, 50)), float(np.percentile(arr, 95))
    except ImportError:
        sorted_vals = sorted(latencies_ms)
        return _percentile(sorted_vals, 50), _percentile(sorted_vals, 95)


def _count_fields(payload: dict[str, Any], prefix: str = "") -> int:
    """Recursively count total leaf fields in a nested dict."""
    count = 0
    for k, v in payload.items():
        full = f"{prefix}.{k}" if prefix else k
        _ = full  # used for potential future path tracking
        if isinstance(v, dict):
            count += _count_fields(v)
        elif isinstance(v, list) and v and isinstance(v[0], dict):
            count += _count_fields(v[0])
        else:
            count += 1
    return count


class JudgeAgent(BaseAgent):
    """Benchmarks an adapter and produces an ArenaScore."""

    name: str = "judge"
    role: Role = Role.REVIEWER
    tool_allowlist: list[str] = ["run_benchmark", "score_api", "update_leaderboard"]
    model: str = "sonnet-4.6"

    def __init__(
        self,
        adapter: BaseAdapter | None = None,
        llm_complete: Any | None = None,
        query: dict[str, Any] | None = None,
    ) -> None:
        self._adapter = adapter
        self._llm_complete = llm_complete
        self._query: dict[str, Any] = query if query is not None else dict(_DEFAULT_QUERY)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def loop(self, input_data: dict[str, Any]) -> AgentResult:
        """Run benchmark and return AgentResult containing ArenaScore.

        Args:
            input_data: Must contain ``project_id`` (UUID or str).
                        Optional: ``adapter_version`` (str).
        """
        start = time.monotonic()
        tool_calls_made: list[str] = []

        # Step 1: validate adapter
        if self._adapter is None:
            return self._failure("no adapter provided", start)

        project_id_raw = input_data.get("project_id")
        if not project_id_raw:
            return self._failure("missing project_id", start)
        project_id = (
            project_id_raw
            if isinstance(project_id_raw, UUID)
            else UUID(str(project_id_raw))
        )
        _ = project_id  # stored for future DB writes (Fas 5b)
        adapter_version: str = str(
            input_data.get("adapter_version", getattr(self._adapter, "version", "unknown"))
        )

        logger.info(
            f"JudgeAgent: starting benchmark adapter={self._adapter.name} "
            f"runs={BENCHMARK_RUNS} project_id={project_id}"
        )

        # Step 2: run BENCHMARK_RUNS fetches, measure latency
        tool_calls_made.append("run_benchmark")
        latencies_ms: list[float] = []
        payloads: list[dict[str, Any]] = []
        error_messages: list[str] = []

        for run_idx in range(BENCHMARK_RUNS):
            run_start = time.monotonic()
            try:
                async for record in self._adapter.fetch(self._query):  # type: ignore[arg-type]
                    payloads.append(record.payload)
                    break  # one record per run is sufficient
                elapsed_ms = (time.monotonic() - run_start) * 1000.0
                latencies_ms.append(elapsed_ms)
                logger.debug(
                    f"JudgeAgent: run {run_idx + 1}/{BENCHMARK_RUNS} "
                    f"latency={elapsed_ms:.1f}ms"
                )
            except Exception as exc:  # noqa: BLE001
                elapsed_ms = (time.monotonic() - run_start) * 1000.0
                latencies_ms.append(elapsed_ms)
                error_messages.append(str(exc))
                logger.warning(f"JudgeAgent: run {run_idx + 1} error: {exc}")

        # Step 3: compute p50, p95
        p50, p95 = _compute_p50_p95(latencies_ms)
        logger.info(f"JudgeAgent: latency p50={p50:.1f}ms p95={p95:.1f}ms")

        # Step 4: count fields per response (max over all runs)
        fields_per_response = 0
        sample_payload: dict[str, Any] = {}
        for payload in payloads:
            fc = _count_fields(payload)
            if fc > fields_per_response:
                fields_per_response = fc
                sample_payload = payload

        # Step 5: estimate cost_per_1k from adapter config (free -> 0.0)
        cost_per_1k: float = 0.0
        if hasattr(self._adapter, "manifest"):
            try:
                manifest = self._adapter.manifest()
                cost_per_1k = float(getattr(manifest, "cost_per_1k_usd", 0.0))
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"JudgeAgent: manifest cost read failed: {exc}")

        # Step 6: LLM call for DX-score
        tool_calls_made.append("score_api")
        dx_score = await self._call_llm_for_dx(
            adapter_name=self._adapter.name,
            sample_payload=sample_payload,
            p50=p50,
            error_messages=error_messages,
        )

        # Step 7: produce ArenaScore
        tool_calls_made.append("update_leaderboard")
        score = ArenaScore(
            adapter_name=self._adapter.name,
            adapter_version=adapter_version,
            latency_p50_ms=round(p50, 2),
            latency_p95_ms=round(p95, 2),
            fields_per_response=fields_per_response,
            cost_per_1k_usd=cost_per_1k,
            dx_score=dx_score,
            measured_at=datetime.now(tz=timezone.utc),
        )
        logger.info(
            f"JudgeAgent: ArenaScore produced "
            f"dx={dx_score:.3f} p50={p50:.1f}ms fields={fields_per_response}"
        )

        # Step 8: return AgentResult
        duration_ms = int((time.monotonic() - start) * 1000)
        return AgentResult(
            agent_name=self.name,
            success=True,
            output={"arena_score": score.model_dump(mode="json")},
            tool_calls_made=tool_calls_made,
            cost_usd=0.0,
            duration_ms=duration_ms,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _call_llm_for_dx(
        self,
        adapter_name: str,
        sample_payload: dict[str, Any],
        p50: float,
        error_messages: list[str],
    ) -> float:
        """Call LLM to score DX. Returns clamped float in [0.0, 1.0]."""
        if self._llm_complete is None:
            from packages.llm.litellm_wrapper import complete  # noqa: PLC0415

            llm_complete = complete
        else:
            llm_complete = self._llm_complete

        user_prompt = build_dx_prompt(
            adapter_name=adapter_name,
            sample_response=sample_payload,
            latency_p50_ms=p50,
            error_messages=error_messages,
        )

        try:
            result = await llm_complete(
                project_id=None,
                agent_id=self.name,
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": DX_SYSTEM_PROMPT + "\n\n" + DX_EXAMPLES,
                    },
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
            )
            raw_content: str = (
                result
                if isinstance(result, str)
                else str(getattr(result, "content", result))
            )
            parsed = json.loads(raw_content)
            raw_score = float(parsed["dx_score"])
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"JudgeAgent: DX LLM call failed: {exc}; defaulting to 0.5")
            raw_score = 0.5

        # Clamp to [0.0, 1.0]
        clamped = max(0.0, min(1.0, raw_score))
        if clamped != raw_score:
            logger.warning(
                f"JudgeAgent: dx_score {raw_score} out of [0,1]; clamped to {clamped}"
            )
        return clamped

    def _failure(
        self,
        reason: str,
        start: float,
        tool_calls_made: list[str] | None = None,
        cost: float = 0.0,
    ) -> AgentResult:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.error(f"JudgeAgent: failure -- {reason}")
        return AgentResult(
            agent_name=self.name,
            success=False,
            output={"error": reason},
            tool_calls_made=tool_calls_made or [],
            cost_usd=cost,
            duration_ms=duration_ms,
        )
