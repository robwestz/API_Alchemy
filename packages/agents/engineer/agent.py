"""EngineerAgent -- genererar API-adaptrar fran dokumentation.

Workflow:
1. Hamta API-doc via httpx
2. Extrahera AdapterDraft via LLM (Instructor + LiteLLM-wrapper)
3. Generera adapter-kod fran AdapterDraft (template-baserat, deterministiskt)
4. Skriv kod till adapters/_generated/<name>/v1/
5. Kor i SandboxRunner (network=none default)
6. Logga MANUAL APPROVAL REQUIRED (human-in-the-loop kommer i Fas 3b)
7. Returnera AgentResult

Per ENGINEER_AGENT_SPEC.md, ARCHITECTURE.md sektion 3 Loop 2 (self-extending).
Inga LLM-anrop utanfor litellm_wrapper.complete(). All API-kunskap inom denna modul.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any
from uuid import UUID

from loguru import logger
from pydantic import BaseModel, Field

from packages.agents.engineer.prompts import (
    EXAMPLES,
    SYSTEM_PROMPT,
    build_user_prompt,
)
from packages.interfaces import (
    AgentResult,
    BaseAgent,
    Role,
    SandboxResult,
    SandboxRunner,
)

__all__ = ["AdapterDraft", "EndpointSpec", "EngineerAgent"]


class EndpointSpec(BaseModel):
    """En endpoint inom en API. Del av AdapterDraft."""

    path: str
    method: str = "GET"
    query_params: list[str] = Field(default_factory=list)
    response_fields: dict[str, str] = Field(default_factory=dict)
    requires_auth: bool = False
    auth_header: str | None = None


class AdapterDraft(BaseModel):
    """Strukturerad output fran Engineer-LLM.

    Per packages/agents/engineer/prompts.py SYSTEM_PROMPT.
    """

    api_name: str
    base_url: str
    endpoints: list[EndpointSpec]
    secrets_required: list[str] = Field(default_factory=list)
    rate_limit_hint: str | None = None
    doc_url: str
    llm_confidence: float = Field(ge=0.0, le=1.0)


MAX_COST_PER_GENERATION_USD = 5.0
MAX_RETRIES = 3
DEFAULT_DOC_TIMEOUT_S = 30.0
DEFAULT_SANDBOX_TIMEOUT_MS = 30_000

GENERATED_ROOT = Path("adapters/_generated")


def _python_type_for(api_type: str) -> str:
    mapping = {
        "str": "str",
        "int": "int",
        "float": "float",
        "bool": "bool",
        "list": "list[Any]",
        "dict": "dict[str, Any]",
    }
    return mapping.get(api_type, "Any")


def _camel_case(snake: str) -> str:
    return "".join(part.capitalize() for part in snake.split("_") if part)


def _render_pydantic_model(draft: AdapterDraft) -> str:
    if not draft.endpoints:
        return ""
    endpoint = draft.endpoints[0]
    lines = ["from typing import Any", "from pydantic import BaseModel", "", ""]
    class_name = f"{_camel_case(draft.api_name)}Response"
    lines.append(f"class {class_name}(BaseModel):")
    if not endpoint.response_fields:
        lines.append("    payload: dict[str, Any]")
    else:
        for field, ftype in sorted(endpoint.response_fields.items()):
            safe = field.replace(".", "_").replace("-", "_")
            lines.append(f"    {safe}: {_python_type_for(ftype)} | None = None")
    return "\n".join(lines) + "\n"


def _render_adapter_class(draft: AdapterDraft) -> str:
    if not draft.endpoints:
        return ""
    endpoint = draft.endpoints[0]
    class_name = _camel_case(draft.api_name) + "Adapter"
    secrets_list = repr(list(draft.secrets_required))
    lines = [
        f'"""Auto-genererad adapter for {draft.api_name}. DO NOT EDIT BY HAND."""',
        "",
        "from __future__ import annotations",
        "",
        "import hashlib",
        "import json",
        "from collections.abc import AsyncIterator",
        "from datetime import datetime, timezone",
        "from typing import Any",
        "from uuid import UUID, uuid4",
        "",
        "import httpx",
        "from loguru import logger",
        "",
        "from packages.interfaces import (",
        "    AdapterManifest,",
        "    AdapterStatus,",
        "    BaseAdapter,",
        "    Record,",
        "    SecretsResolver,",
        ")",
        "",
        f'_BASE_URL = "{draft.base_url}{endpoint.path}"',
        f'_ADAPTER_NAME = "{draft.api_name}"',
        '_ADAPTER_VERSION = "1.0.0"',
        f"_SECRETS_REQUIRED = {secrets_list}",
        "",
        "",
        f"class {class_name}(BaseAdapter):",
        f'    """Auto-genererad adapter for {draft.api_name}."""',
        "",
        "    name: str = _ADAPTER_NAME",
        "    version: str = _ADAPTER_VERSION",
        '    schema_hash: str = ""',
        "    secrets_required: list[str] = _SECRETS_REQUIRED",
        "",
        "    def __init__(self, project_id: UUID | None = None) -> None:",
        "        self._project_id = project_id if project_id is not None else uuid4()",
        "",
        "    def fetch(  # type: ignore[override]",
        "        self,",
        "        query: dict[str, Any],",
        "        secrets: SecretsResolver | None = None,",
        "    ) -> AsyncIterator[Record]:",
        "        return self._fetch_generator(query, secrets)",
        "",
        "    async def _fetch_generator(",
        "        self,",
        "        query: dict[str, Any],",
        "        secrets: SecretsResolver | None,",
        "    ) -> AsyncIterator[Record]:",
        "        headers: dict[str, str] = {}",
        "        if _SECRETS_REQUIRED and secrets is not None:",
        "            for key in _SECRETS_REQUIRED:",
        "                value = await secrets.get(self._project_id, key)",
        '                headers["Authorization"] = f"Bearer {value}"',
        "                break",
        "        async with httpx.AsyncClient(timeout=30.0) as client:",
        "            response = await client.get(",
        "                _BASE_URL,",
        "                params={k: str(v) for k, v in query.items()},",
        "                headers=headers,",
        "            )",
        "            response.raise_for_status()",
        "            data: dict[str, Any] = response.json()",
        "        canonical = json.dumps(sorted(_keys(data)), sort_keys=True)",
        "        schema_hash = hashlib.sha256(canonical.encode()).hexdigest()",
        "        yield Record(",
        "            project_id=self._project_id,",
        "            adapter_name=_ADAPTER_NAME,",
        "            adapter_version=_ADAPTER_VERSION,",
        "            schema_hash=schema_hash,",
        "            payload=data,",
        "            fetched_at=datetime.now(tz=timezone.utc),",
        '            lineage={"source_url": _BASE_URL},',
        "        )",
        "",
        "    def manifest(self) -> AdapterManifest:",
        "        return AdapterManifest(",
        "            name=_ADAPTER_NAME,",
        "            version=_ADAPTER_VERSION,",
        '            schema_hash="",',
        f'            doc_url="{draft.doc_url}",',
        "            generated_at=datetime.now(tz=timezone.utc),",
        '            model_used="opus-4.7",',
        "            prompts_used=[],",
        "            secrets_required=_SECRETS_REQUIRED,",
        "            status=AdapterStatus.GENERATED,",
        "        )",
        "",
        "",
        'def _keys(obj: Any, prefix: str = "") -> list[str]:',
        "    paths: list[str] = []",
        "    if isinstance(obj, dict):",
        "        for k, v in obj.items():",
        '            full = f"{prefix}.{k}" if prefix else k',
        "            paths.append(full)",
        "            paths.extend(_keys(v, full))",
        "    elif isinstance(obj, list) and obj:",
        "        paths.extend(_keys(obj[0], prefix))",
        "    return paths",
    ]
    return "\n".join(lines) + "\n"


def _render_minimal_test(draft: AdapterDraft) -> str:
    class_name = _camel_case(draft.api_name) + "Adapter"
    return (
        f'"""Sandbox-test for auto-genererad adapter {draft.api_name}."""\n'
        f"\n"
        f"import asyncio\n"
        f"from unittest.mock import AsyncMock, MagicMock, patch\n"
        f"from uuid import uuid4\n"
        f"\n"
        f"from {draft.api_name}_adapter import {class_name}\n"
        f"\n"
        f"\n"
        f"async def main() -> None:\n"
        f"    adapter = {class_name}(project_id=uuid4())\n"
        f"    mock_resp = MagicMock()\n"
        f"    mock_resp.raise_for_status = MagicMock()\n"
        f'    mock_resp.json = MagicMock(return_value={{"ok": True}})\n'
        f'    with patch("httpx.AsyncClient") as mock_client_cls:\n'
        f"        mock_client = AsyncMock()\n"
        f"        mock_client.__aenter__ = AsyncMock(return_value=mock_client)\n"
        f"        mock_client.__aexit__ = AsyncMock(return_value=None)\n"
        f"        mock_client.get = AsyncMock(return_value=mock_resp)\n"
        f"        mock_client_cls.return_value = mock_client\n"
        f"        async for rec in adapter.fetch({{}}):\n"
        f'            print(f"OK schema_hash={{rec.schema_hash[:12]}}...")\n'
        f"            break\n"
        f"\n"
        f"\n"
        f'if __name__ == "__main__":\n'
        f"    asyncio.run(main())\n"
    )


class EngineerAgent(BaseAgent):
    """Genererar adapter-kod fran API-doc URL."""

    name: str = "engineer"
    role: Role = Role.EXECUTOR
    tool_allowlist: list[str] = [
        "read_doc",
        "write_pydantic_model",
        "write_adapter",
        "sandbox_test",
        "register_adapter",
    ]
    model: str = "opus-4.7"

    def __init__(
        self,
        sandbox: SandboxRunner,
        llm_complete: Any | None = None,
        generated_root: Path | None = None,
    ) -> None:
        self._sandbox = sandbox
        self._llm_complete = llm_complete
        self._generated_root = generated_root or GENERATED_ROOT

    async def loop(self, input_data: dict[str, Any]) -> AgentResult:
        start = time.monotonic()
        doc_url = input_data.get("doc_url")
        project_id_raw = input_data.get("project_id")
        if not doc_url or not project_id_raw:
            return self._failure("missing doc_url or project_id", start)
        project_id = (
            project_id_raw
            if isinstance(project_id_raw, UUID)
            else UUID(str(project_id_raw))
        )

        cumulative_cost = 0.0
        tool_calls_made: list[str] = []

        try:
            doc_content = await self._fetch_doc(doc_url)
            tool_calls_made.append("read_doc")
        except Exception as exc:  # noqa: BLE001
            logger.error(f"EngineerAgent: doc-fetch failed: {exc}")
            return self._failure(f"doc-fetch failed: {exc}", start, tool_calls_made)

        draft: AdapterDraft | None = None
        last_error: str | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            if cumulative_cost >= MAX_COST_PER_GENERATION_USD:
                return self._failure(
                    f"cost-cap ${MAX_COST_PER_GENERATION_USD} exceeded",
                    start,
                    tool_calls_made,
                    cost=cumulative_cost,
                )
            try:
                draft, attempt_cost = await self._extract_draft(
                    doc_url=doc_url,
                    doc_content=doc_content,
                    project_id=project_id,
                )
                cumulative_cost += attempt_cost
                logger.info(
                    f"EngineerAgent: AdapterDraft attempt={attempt} "
                    f"confidence={draft.llm_confidence:.2f}"
                )
                break
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                logger.warning(
                    f"EngineerAgent: LLM attempt {attempt}/{MAX_RETRIES} failed: {exc}"
                )

        if draft is None:
            return self._failure(
                f"LLM extraction failed: {last_error}",
                start,
                tool_calls_made,
                cost=cumulative_cost,
            )
        tool_calls_made.append("write_pydantic_model")

        pydantic_code = _render_pydantic_model(draft)
        adapter_code = _render_adapter_class(draft)
        test_code = _render_minimal_test(draft)
        tool_calls_made.append("write_adapter")

        target_dir = self._generated_root / draft.api_name / "v1"
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "model.py").write_text(pydantic_code, encoding="utf-8")
        (target_dir / f"{draft.api_name}_adapter.py").write_text(
            adapter_code, encoding="utf-8"
        )
        (target_dir / "sandbox_test.py").write_text(test_code, encoding="utf-8")
        prompt_hash = hashlib.sha256(
            (
                SYSTEM_PROMPT
                + EXAMPLES
                + build_user_prompt(doc_content[:500], doc_url)
            ).encode()
        ).hexdigest()
        (target_dir / "manifest.json").write_text(
            self._render_manifest_json(draft, prompt_hash, cumulative_cost),
            encoding="utf-8",
        )
        logger.info(f"EngineerAgent: code written to {target_dir}")

        sandbox_result: SandboxResult | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                tool_calls_made.append("sandbox_test")
                sandbox_result = await self._sandbox.run(
                    code=test_code,
                    secrets={},
                    network_policy="none",
                    timeout_ms=DEFAULT_SANDBOX_TIMEOUT_MS,
                )
                if sandbox_result.success:
                    logger.info(
                        f"EngineerAgent: sandbox PASS attempt={attempt}"
                    )
                    break
                logger.warning(
                    f"EngineerAgent: sandbox FAIL attempt={attempt} "
                    f"exit={sandbox_result.exit_code}"
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(f"EngineerAgent: sandbox crash attempt={attempt}: {exc}")
                last_error = str(exc)

        if sandbox_result is None or not sandbox_result.success:
            return self._failure(
                f"sandbox validation failed after {MAX_RETRIES} retries",
                start,
                tool_calls_made,
                cost=cumulative_cost,
                output={
                    "draft": draft.model_dump(),
                    "target_dir": str(target_dir),
                    "sandbox_result": sandbox_result.model_dump()
                    if sandbox_result
                    else None,
                },
            )

        logger.warning(
            "EngineerAgent: MANUAL APPROVAL REQUIRED -- "
            f"adapter status sandbox_passed. Operator maste granska {target_dir}."
        )

        duration_ms = int((time.monotonic() - start) * 1000)
        tool_calls_made.append("register_adapter")
        return AgentResult(
            agent_name=self.name,
            success=True,
            output={
                "draft": draft.model_dump(),
                "target_dir": str(target_dir),
                "sandbox_result": sandbox_result.model_dump(),
                "manual_approval_required": True,
            },
            tool_calls_made=tool_calls_made,
            cost_usd=cumulative_cost,
            duration_ms=duration_ms,
        )

    async def _fetch_doc(self, doc_url: str) -> str:
        import httpx  # noqa: PLC0415

        async with httpx.AsyncClient(timeout=DEFAULT_DOC_TIMEOUT_S) as client:
            response = await client.get(doc_url)
            response.raise_for_status()
            return response.text

    async def _extract_draft(
        self,
        doc_url: str,
        doc_content: str,
        project_id: UUID,
    ) -> tuple[AdapterDraft, float]:
        if self._llm_complete is None:
            from packages.llm.litellm_wrapper import complete  # noqa: PLC0415

            llm_complete = complete
        else:
            llm_complete = self._llm_complete

        user_prompt = build_user_prompt(doc_content, doc_url)
        result = await llm_complete(
            project_id=project_id,
            agent_id=self.name,
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + EXAMPLES},
                {"role": "user", "content": user_prompt},
            ],
            response_model=AdapterDraft,
            temperature=0.2,
        )
        if isinstance(result, AdapterDraft):
            return result, 0.0
        cost = float(getattr(result, "cost_usd", 0.0))
        if hasattr(result, "structured") and isinstance(result.structured, AdapterDraft):
            return result.structured, cost
        import json  # noqa: PLC0415

        content = getattr(result, "content", str(result))
        return AdapterDraft.model_validate(json.loads(content)), cost

    @staticmethod
    def _render_manifest_json(
        draft: AdapterDraft,
        prompt_hash: str,
        cost_usd: float,
    ) -> str:
        import json  # noqa: PLC0415
        from datetime import datetime, timezone  # noqa: PLC0415

        manifest = {
            "name": draft.api_name,
            "version": "1.0.0",
            "schema_hash": "",
            "doc_url": draft.doc_url,
            "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            "model_used": "opus-4.7",
            "prompts_used": [prompt_hash],
            "secrets_required": list(draft.secrets_required),
            "status": "generated",
            "llm_confidence": draft.llm_confidence,
            "generation_cost_usd": cost_usd,
        }
        return json.dumps(manifest, indent=2, sort_keys=True) + "\n"

    def _failure(
        self,
        reason: str,
        start: float,
        tool_calls_made: list[str] | None = None,
        cost: float = 0.0,
        output: dict[str, Any] | None = None,
    ) -> AgentResult:
        duration_ms = int((time.monotonic() - start) * 1000)
        return AgentResult(
            agent_name=self.name,
            success=False,
            output={"error": reason, **(output or {})},
            tool_calls_made=tool_calls_made or [],
            cost_usd=cost,
            duration_ms=duration_ms,
        )
