"""ScoutAgent -- discovery av relevanta publika API:er per doman.

Workflow:
1. (Optional) web_search_fn for initial URL-kandidater
2. (Optional) web_fetch_fn for snippets / doc-content
3. LLM-anrop (via litellm_wrapper.complete) -> DiscoveryReport
4. Cost-cap-check
5. Returnera AgentResult med DiscoveryReport som output

Per ARCHITECTURE.md sektion 3 Loop 1 (self-discovering).
Inga LLM-anrop utanfor litellm_wrapper.complete().
"""

from __future__ import annotations

import time
from typing import Any
from uuid import UUID

from loguru import logger

from packages.agents.scout.prompts import (
    EXAMPLES,
    SYSTEM_PROMPT,
    build_user_prompt,
)
from packages.interfaces import (
    AgentResult,
    BaseAgent,
    DiscoveryReport,
    Role,
)

__all__ = ["ScoutAgent"]


MAX_COST_PER_DISCOVERY_USD = 2.0
MAX_RETRIES = 3
DEFAULT_MAX_CANDIDATES = 5
DEFAULT_FETCH_TIMEOUT_S = 15.0


class ScoutAgent(BaseAgent):
    """Discovery: doman -> rankad lista av API-kandidater."""

    name: str = "scout"
    role: Role = Role.EXECUTOR
    tool_allowlist: list[str] = ["web_search", "web_fetch", "read_docs", "evaluate_api"]
    model: str = "sonnet-4.6"

    def __init__(
        self,
        llm_complete: Any | None = None,
        web_search_fn: Any | None = None,
        web_fetch_fn: Any | None = None,
    ) -> None:
        self._llm_complete = llm_complete
        self._web_search_fn = web_search_fn
        self._web_fetch_fn = web_fetch_fn

    async def loop(self, input_data: dict[str, Any]) -> AgentResult:
        start = time.monotonic()
        domain = input_data.get("domain")
        project_id_raw = input_data.get("project_id")
        max_candidates = int(input_data.get("max_candidates", DEFAULT_MAX_CANDIDATES))

        if not domain or not project_id_raw:
            return self._failure("missing domain or project_id", start)
        project_id = (
            project_id_raw
            if isinstance(project_id_raw, UUID)
            else UUID(str(project_id_raw))
        )

        cumulative_cost = 0.0
        tool_calls_made: list[str] = []

        search_results: list[dict[str, Any]] = []
        if self._web_search_fn is not None:
            try:
                tool_calls_made.append("web_search")
                search_results = await self._web_search_fn(domain)
                logger.info(
                    f"ScoutAgent: web_search returned {len(search_results)} hits"
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"ScoutAgent: web_search failed: {exc}")

        fetched_snippets: list[dict[str, str]] = []
        for hit in search_results[:5]:
            url = hit.get("url", "")
            if not url:
                continue
            try:
                tool_calls_made.append("web_fetch")
                content = await self._fetch_url(url)
                fetched_snippets.append(
                    {"url": url, "title": hit.get("title", ""), "content": content[:2000]}
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"ScoutAgent: fetch failed for {url}: {exc}")

        report: DiscoveryReport | None = None
        last_error: str | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            if cumulative_cost >= MAX_COST_PER_DISCOVERY_USD:
                return self._failure(
                    f"cost-cap ${MAX_COST_PER_DISCOVERY_USD} exceeded",
                    start,
                    tool_calls_made,
                    cost=cumulative_cost,
                )
            try:
                tool_calls_made.append("evaluate_api")
                report, attempt_cost = await self._extract_report(
                    domain=domain,
                    project_id=project_id,
                    max_candidates=max_candidates,
                    search_results=search_results,
                    fetched_snippets=fetched_snippets,
                )
                cumulative_cost += attempt_cost
                logger.info(
                    f"ScoutAgent: DiscoveryReport attempt={attempt} "
                    f"candidates={len(report.candidates)}"
                )
                break
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                logger.warning(
                    f"ScoutAgent: LLM attempt {attempt}/{MAX_RETRIES} failed: {exc}"
                )

        if report is None:
            return self._failure(
                f"LLM extraction failed: {last_error}",
                start,
                tool_calls_made,
                cost=cumulative_cost,
            )

        duration_ms = int((time.monotonic() - start) * 1000)
        return AgentResult(
            agent_name=self.name,
            success=True,
            output={
                "discovery_report": report.model_dump(mode="json"),
                "candidate_count": len(report.candidates),
                "search_results_used": len(search_results),
            },
            tool_calls_made=tool_calls_made,
            cost_usd=cumulative_cost,
            duration_ms=duration_ms,
        )

    async def _fetch_url(self, url: str) -> str:
        if self._web_fetch_fn is not None:
            return await self._web_fetch_fn(url)

        import httpx  # noqa: PLC0415

        async with httpx.AsyncClient(timeout=DEFAULT_FETCH_TIMEOUT_S) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text

    async def _extract_report(
        self,
        domain: str,
        project_id: UUID,
        max_candidates: int,
        search_results: list[dict[str, Any]],
        fetched_snippets: list[dict[str, str]],
    ) -> tuple[DiscoveryReport, float]:
        if self._llm_complete is None:
            from packages.llm.litellm_wrapper import complete  # noqa: PLC0415

            llm_complete = complete
        else:
            llm_complete = self._llm_complete

        user_prompt = build_user_prompt(domain=domain, max_candidates=max_candidates)
        if search_results:
            user_prompt += "\n\nSearch results found:\n"
            for i, hit in enumerate(search_results[:10], 1):
                user_prompt += (
                    f"{i}. {hit.get('title', '')}\n"
                    f"   URL: {hit.get('url', '')}\n"
                    f"   Snippet: {hit.get('snippet', '')}\n"
                )
        if fetched_snippets:
            user_prompt += "\n\nFetched doc snippets:\n"
            for snip in fetched_snippets[:5]:
                user_prompt += (
                    f"--- {snip.get('url', '')} ---\n"
                    f"{snip.get('content', '')[:1500]}\n"
                )

        result = await llm_complete(
            project_id=project_id,
            agent_id=self.name,
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + EXAMPLES},
                {"role": "user", "content": user_prompt},
            ],
            response_model=DiscoveryReport,
            temperature=0.3,
        )
        if isinstance(result, DiscoveryReport):
            return result, 0.0
        cost = float(getattr(result, "cost_usd", 0.0))
        if hasattr(result, "structured") and isinstance(result.structured, DiscoveryReport):
            return result.structured, cost
        import json  # noqa: PLC0415

        content = getattr(result, "content", str(result))
        return DiscoveryReport.model_validate(json.loads(content)), cost

    def _failure(
        self,
        reason: str,
        start: float,
        tool_calls_made: list[str] | None = None,
        cost: float = 0.0,
    ) -> AgentResult:
        duration_ms = int((time.monotonic() - start) * 1000)
        return AgentResult(
            agent_name=self.name,
            success=False,
            output={"error": reason},
            tool_calls_made=tool_calls_made or [],
            cost_usd=cost,
            duration_ms=duration_ms,
        )
