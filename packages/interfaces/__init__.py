"""API Alchemy Engine -- karnabstraktioner.

Definierar kontrakten som senare faser bygger emot:
  - BaseAdapter: API-adapter-kontrakt
  - BaseAgent: runtime-agent-kontrakt
  - ToolSpec / ToolRegistry: action-parity-mekanism
  - ProjectState: delat state mellan UI och agent
  - SandboxRunner: sandbox-abstraktion (E2B / Codespaces / LocalProcess)
  - SecretsResolver: secrets-abstraktion (Doppler / LocalToml)
  - ReplayCursor: historisk replay av records taggade med adapter_version
  - Record / DiscoveryReport / AdapterManifest / ArenaScore: Pydantic-modeller

Mypy strict-kompatibel. Inga implementationer har -- endast Protocol/ABC-kontrakt.
Se ../../ARCHITECTURE.md sektion 2 for helhetsbild.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import datetime
from enum import Enum
from typing import Any, Generic, Protocol, TypeVar, runtime_checkable
from uuid import UUID

from pydantic import BaseModel, Field

__all__ = [
    "AdapterManifest",
    "AdapterStatus",
    "AgentResult",
    "ArenaScore",
    "BaseAdapter",
    "BaseAgent",
    "DiscoveryCandidate",
    "DiscoveryReport",
    "ProjectState",
    "Record",
    "ReplayCursor",
    "Role",
    "SandboxResult",
    "SandboxRunner",
    "SecretsResolver",
    "ToolRegistry",
    "ToolSpec",
]


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Role(str, Enum):
    """Build-time och runtime roller. Per AGENT_ROLES.md sektion 3."""

    PLANNER = "planner"
    EXECUTOR = "executor"
    REVIEWER = "reviewer"
    VERIFIER = "verifier"
    OPERATOR = "operator"


class AdapterStatus(str, Enum):
    """Adapter-livscykel. Per ARCHITECTURE.md Loop 2 (self-extending)."""

    GENERATED = "generated"
    SANDBOX_PASSED = "sandbox_passed"
    HUMAN_APPROVED = "human_approved"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


# ---------------------------------------------------------------------------
# Records & manifests (Pydantic models)
# ---------------------------------------------------------------------------


class Record(BaseModel):
    """En rad i Lake `records`-tabellen.

    JSONB-payload validerat via adapter-specifik Pydantic-modell. `adapter_version`
    kravs for replay-pinning (se ReplayCursor).
    """

    project_id: UUID
    adapter_name: str
    adapter_version: str
    schema_hash: str
    payload: dict[str, Any]
    fetched_at: datetime
    lineage: dict[str, Any] = Field(default_factory=dict)


class AdapterManifest(BaseModel):
    """Manifest for en genererad adapter. Lagras i Lake `adapter_manifests`."""

    name: str
    version: str
    schema_hash: str
    doc_url: str
    generated_at: datetime
    model_used: str
    prompts_used: list[str]
    secrets_required: list[str] = Field(default_factory=list)
    status: AdapterStatus = AdapterStatus.GENERATED


class DiscoveryCandidate(BaseModel):
    """En API-kandidat fran Scout. Del av DiscoveryReport."""

    api_name: str
    doc_url: str
    estimated_cost_per_1k: float
    data_coverage: str
    reliability_score: float
    requires_secret: bool


class DiscoveryReport(BaseModel):
    """Output fran Scout-agent. Per PHASE_PLAN.md Fas 4."""

    project_id: UUID
    domain: str
    candidates: list[DiscoveryCandidate]
    cost_usd: float
    generated_at: datetime


class ArenaScore(BaseModel):
    """Output fran Judge-agent per adapter. Per PHASE_PLAN.md Fas 5."""

    adapter_name: str
    adapter_version: str
    latency_p50_ms: float
    latency_p95_ms: float
    fields_per_response: int
    cost_per_1k_usd: float
    dx_score: float
    measured_at: datetime


class SandboxResult(BaseModel):
    """Output fran SandboxRunner.run."""

    success: bool
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int
    network_calls: list[str] = Field(default_factory=list)


class AgentResult(BaseModel):
    """Output fran BaseAgent.loop."""

    agent_name: str
    success: bool
    output: dict[str, Any]
    tool_calls_made: list[str]
    cost_usd: float
    duration_ms: int


# ---------------------------------------------------------------------------
# ToolSpec / ToolRegistry -- action-parity-mekanismen
# ---------------------------------------------------------------------------


T_Input = TypeVar("T_Input", bound=BaseModel)
T_Output = TypeVar("T_Output", bound=BaseModel)


class ToolSpec(BaseModel, Generic[T_Input, T_Output]):
    """En atomic primitive deklarerad EN gang. Kalla till action parity.

    Frontend renderar UI fran `ui_component`. Agent far anvanda tool om
    `agent_allowed=True`. CI-test verifierar paritet.
    """

    name: str
    description: str
    input_schema: type[T_Input]
    output_schema: type[T_Output]
    handler: Callable[[T_Input], Awaitable[T_Output]]
    agent_allowed: bool = True
    ui_visible: bool = True
    ui_component: str | None = None

    model_config = {"arbitrary_types_allowed": True}


ToolRegistry = dict[str, ToolSpec[Any, Any]]
"""Single source of truth. Definieras i packages/orchestrator/primitives/_registry.py."""


# ---------------------------------------------------------------------------
# BaseAdapter -- kontrakt for API-adaptrar
# ---------------------------------------------------------------------------


class BaseAdapter(ABC):
    """Kontrakt for alla API-adaptrar (manuella och auto-genererade).

    En BaseAdapter exponerar `fetch()` som returnerar en async iterator over
    `Record`-objekt. Adaptern deklarerar vilka secrets den kraver -- sandbox
    levererar endast dessa, aldrig hela vault.
    """

    name: str
    version: str
    schema_hash: str
    secrets_required: list[str]

    @abstractmethod
    def fetch(
        self,
        query: dict[str, Any],
        secrets: SecretsResolver,
    ) -> AsyncIterator[Record]:
        """Hamta records fran upstream API. Yieldar en stream."""
        raise NotImplementedError

    @abstractmethod
    def manifest(self) -> AdapterManifest:
        """Returnera manifestet for denna adapter-version."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# BaseAgent -- kontrakt for runtime-agenter
# ---------------------------------------------------------------------------


class BaseAgent(ABC):
    """Kontrakt for Scout, Engineer, Judge, Profiler m.fl.

    Agent foljer standard-loopen: plan -> tool_call -> observe -> reflect.
    `tool_allowlist` enforce:as av ToolRegistry-handler innan exekvering.
    """

    name: str
    role: Role
    tool_allowlist: list[str]
    model: str

    @abstractmethod
    async def loop(self, input_data: dict[str, Any]) -> AgentResult:
        """Kor agentens huvud-loop tills mal uppnatt eller cap-traff."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# ProjectState -- delat state-trad mellan UI och agent
# ---------------------------------------------------------------------------


@runtime_checkable
class ProjectState(Protocol):
    """Wraps Lake `records` + WebSocket-broadcast.

    UI och agent laser/skriver via samma instans. Skrivningar broadcast:as
    automatiskt till alla subscribers pa topic `project:<id>`.
    """

    project_id: UUID

    async def read(self, key: str) -> Any: ...

    async def write(self, key: str, value: Any) -> None: ...

    def subscribe(self, topic: str) -> AsyncIterator[dict[str, Any]]: ...


# ---------------------------------------------------------------------------
# SandboxRunner -- abstraherar E2B / Codespaces / LocalProcess
# ---------------------------------------------------------------------------


class SandboxRunner(ABC):
    """Kor auto-genererad adapter-kod isolerat. R1-mitigering.

    Default `network_policy="none"`. Adapter-manifest kan begara specifika
    domaner; dessa ges som allowlist till sandbox.
    """

    @abstractmethod
    async def run(
        self,
        code: str,
        secrets: dict[str, str],
        network_policy: str = "none",
        timeout_ms: int = 30_000,
    ) -> SandboxResult:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# SecretsResolver -- abstraherar Doppler / LocalToml
# ---------------------------------------------------------------------------


@runtime_checkable
class SecretsResolver(Protocol):
    """Hamtar specifika secrets per request. Aldrig hela vault.

    Implementations: DopplerResolver (online), LocalTomlResolver (offline).
    """

    async def get(self, project_id: UUID, key: str) -> str: ...

    async def get_many(self, project_id: UUID, keys: list[str]) -> dict[str, str]: ...


# ---------------------------------------------------------------------------
# ReplayCursor -- historisk replay
# ---------------------------------------------------------------------------


class ReplayCursor(ABC):
    """Laser records som de sag ut vid en specifik tidpunkt eller adapter-version.

    Per DECISIONS.md D7 (schema-evolution) och V1 (replay-mode).
    """

    project_id: UUID

    @abstractmethod
    def at(self, until_ts: datetime) -> AsyncIterator[Record]:
        """Yieldar records som existerade vid `until_ts`."""
        raise NotImplementedError

    @abstractmethod
    def for_adapter_version(
        self,
        adapter_name: str,
        version: str,
    ) -> AsyncIterator[Record]:
        """Yieldar records producerade av specifik adapter-version."""
        raise NotImplementedError
