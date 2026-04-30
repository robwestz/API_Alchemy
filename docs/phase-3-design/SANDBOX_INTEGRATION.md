# SANDBOX_INTEGRATION — Fas 3 Design

> Draft av Architect-draft (Sonnet). Review av Lead Architect (Opus) krävs innan Fas 3 öppnas.
> Datum: 2026-04-29. Baserat på DECISIONS.md D4, RISK_REGISTER.md R1/R11, ARCHITECTURE.md sektion 8.
> Implementationsfil: `packages/sandbox/e2b_runner.py` (per DOD_MATRIX.md Fas 3).

---

## 1. Paket-setup

E2B SDK läggs till som optional extra i `pyproject.toml`:

```toml
[project.optional-dependencies]
sandbox = [
    "e2b>=0.17.0",
]
sandbox-dev = [
    "pytest-httpx>=0.30.0",   # Mock httpx för unit-tests av E2BSandboxRunner
]
```

Installation i Fas 3:
```bash
pip install -e ".[sandbox]"
pip install -e ".[sandbox-dev]"   # i dev/test-miljö
```

E2B API-nyckel: läses från `SecretsResolver` under nyckelnamnet `E2B_API_KEY`.
Aldrig hårdkodat. Detta är en infrastruktur-secret — ingår INTE i `adapter.secrets_required`.

---

## 2. Klass-hierarki

```
SandboxRunner (ABC, packages/interfaces/__init__.py)
    │
    ├── E2BSandboxRunner          (packages/sandbox/e2b_runner.py)       [DEFAULT]
    ├── CodespacesSandboxRunner   (packages/sandbox/codespaces_runner.py) [FALLBACK]
    └── LocalProcessSandboxRunner (packages/sandbox/local_runner.py)      [--unsafe-local]
```

Val av implementation sker via factory-funktion i `packages/sandbox/__init__.py`:

```python
def get_sandbox_runner(
    config: SandboxConfig,
    secrets: SecretsResolver,
    project_id: UUID,
) -> SandboxRunner:
    if config.backend == "e2b":
        return E2BSandboxRunner(secrets=secrets, project_id=project_id)
    elif config.backend == "codespaces":
        return CodespacesSandboxRunner(secrets=secrets, project_id=project_id)
    elif config.backend == "local":
        if not config.unsafe_local_confirmed:
            raise ValueError("LocalProcessSandboxRunner kräver --unsafe-local flag")
        return LocalProcessSandboxRunner()
    raise ValueError(f"Okänd sandbox backend: {config.backend}")
```

---

## 3. E2BSandboxRunner — run()-flöde

### 3.1 Signatur (implementerar `SandboxRunner` ABC)

```python
async def run(
    self,
    code: str,
    secrets: dict[str, str],
    network_policy: str = "none",
    timeout_ms: int = 30_000,
) -> SandboxResult:
```

### 3.2 Steg-för-steg

**Steg 1 — Skapa ephemeral E2B sandbox**

```python
from e2b import Sandbox

sandbox = await Sandbox.create(
    template="base",            # Python 3.11 base image
    api_key=await self._get_e2b_key(),
    timeout=timeout_ms // 1000 + 10,  # E2B timeout i sekunder, +10s buffer
    metadata={
        "project_id": str(self.project_id),
        "purpose": "adapter_test",
    },
)
```

**Steg 2 — Upload kod-fil + secrets som env-vars**

Kod laddas upp som fil (inte via stdin) för att möjliggöra relativa imports:

```python
await sandbox.filesystem.write("/home/user/adapter_test.py", code)
```

Secrets injiceras som environment-variabler. ENDAST nycklar som adaptern deklarerat
i `secrets_required` — aldrig hela vault. Valideras mot `adapter.secrets_required`
innan upload; extra nycklar avvisas med `SecurityError`.

```python
# Validering
declared = set(adapter.secrets_required)
provided = set(secrets.keys())
extra = provided - declared
if extra:
    raise SecurityError(f"Sandbox fick fler secrets än deklarerat: {extra}")

env_vars = dict(secrets)  # Vidarebefordras till process.start()
```

**Steg 3 — Network-policy**

| `network_policy` värde | E2B-handling |
|---|---|
| `"none"` (default, R1-default) | Sandbox körs med E2B:s default container-isolering. Inga extra nätverkstillstånd beviljas. Utgående anrop förväntas blockeras av container-setup. |
| `"allowlist"` | Anropa `sandbox.set_network_policy(allow_domains=[...])` om E2B SDK stöder det i vald version. Om ej stöds: logga WARNING och fall tillbaka till `"none"`. |

OBS: E2B free tier network-isolation-beteende MÅSTE verifieras i integrationstester
innan Fas 3-DoD godkänns (se OQ-6 och sektion 6.2).

**Steg 4 — Exekvera `python adapter_test.py` med timeout**

```python
process = await sandbox.process.start(
    "cd /home/user && python adapter_test.py",
    env_vars=env_vars,
    on_stdout=lambda e: stdout_buffer.append(e.line),
    on_stderr=lambda e: stderr_buffer.append(e.line),
)
try:
    result = await asyncio.wait_for(
        process.wait(),
        timeout=timeout_ms / 1000,
    )
    exit_code = result.exit_code
except asyncio.TimeoutError:
    await process.kill()
    exit_code = -1
    stderr_buffer.append(f"TIMEOUT after {timeout_ms}ms")
```

**Steg 5 — Capture stdout/stderr/exit_code**

```python
stdout = "\n".join(stdout_buffer)
stderr = "\n".join(stderr_buffer)
success = (exit_code == 0) and ("PASS" in stdout)
```

**Steg 6 — Lista observerade nätverksanrop**

Primär metod: E2B SDK network monitor (om tillgänglig i vald SDK-version).
Fallback: regex-scan av stdout+stderr för typiska Python-nätverksanrop.

```python
try:
    # Primär: SDK-stödd network monitor
    network_calls: list[str] = await sandbox.network.get_connections()
except AttributeError:
    # Fallback: regex-scan (svagare garanti — se OQ-8)
    network_calls = _extract_network_calls_from_output(stdout + stderr)

# R1-enforcement: om network_calls inte är tom och policy är "none"
if network_calls and network_policy == "none":
    logger.error(
        "SECURITY WARNING: adapter-kod försökte göra nätverksanrop trots "
        f"network_policy=none. Anrop: {network_calls}"
    )
    # Propageras till EngineerAgent som abortar utan retry
```

**Steg 7 — Cleanup sandbox**

```python
finally:
    await sandbox.close()
    # E2B sandbox är ephemeral — automatisk destruktion efter close()
    # Inga persistent data kvar i molnet
```

### 3.3 Komplett SandboxResult

```python
return SandboxResult(
    success=success,
    stdout=_redact_secrets(stdout, secrets),
    stderr=_redact_secrets(stderr, secrets),
    exit_code=exit_code,
    duration_ms=int((time.monotonic() - t_start) * 1000),
    network_calls=network_calls,
)
```

Fälten matchar `SandboxResult` från `packages/interfaces/__init__.py` (lines 143–150):
- `success: bool`
- `stdout: str` (secrets redactade)
- `stderr: str` (secrets redactade)
- `exit_code: int`
- `duration_ms: int`
- `network_calls: list[str]`

---

## 4. Fallback-strategi

### 4.1 Trigger-villkor E2B → Codespaces

Fallback triggas vid:
- `RateLimitError` (HTTP 429 från E2B API)
- `SandboxTimeoutError` vid sandbox-skapande (3 försök, exponential backoff)
- Connection timeout > 10s vid sandbox-skapande
- HTTP 402 (dagsgräns uppnådd på free tier)

```python
async def run_with_fallback(
    code: str,
    secrets: dict[str, str],
    network_policy: str,
    timeout_ms: int,
    runners: list[SandboxRunner],  # [E2BSandboxRunner, CodespacesSandboxRunner]
) -> SandboxResult:
    last_error: Exception | None = None
    for runner in runners:
        try:
            return await runner.run(code, secrets, network_policy, timeout_ms)
        except (RateLimitError, SandboxTimeoutError, ConnectionError) as e:
            last_error = e
            logger.warning(
                f"Sandbox {type(runner).__name__} failed: {e}. Försöker nästa backend."
            )
    raise SandboxAllBackendsFailed(
        f"Alla sandbox-backends misslyckades. Sista fel: {last_error}"
    )
```

### 4.2 CodespacesSandboxRunner (fallback)

- **Budget**: 90h/mån via GitHub Education Pack (R11-mitigering).
- **Skapande**: POST `/user/codespaces` via GitHub REST API.
- **Exekvering**: Remote exec via Codespaces API eller SSH.
- **Cleanup**: DELETE `/user/codespaces/{name}` + `auto_delete_timeout = 10` minuter.
- **Latens**: ~30–60s för sandbox-skapande (vs E2B ~2–5s). Acceptabelt för fallback.
- **Network isolation**: Codespaces garanterar INTE network=none på samma sätt som E2B.
  Vid Codespaces-körning loggas alltid WARNING om `network_calls` inte är tom,
  men kör inte abort (eftersom isolationen är svagare och vi vet om det).

### 4.3 LocalProcessSandboxRunner (sista utväg)

- Kräver explicit `--unsafe-local` CLI-flag.
- Kör `python adapter_test.py` som subprocess i isolerad venv.
- **INGEN nätverksisolering** — operatören tar fullt ansvar.
- Loggar `UNSAFE_LOCAL_EXECUTION=true` i `tool_calls_log`.
- Används ALDRIG i CI eller produktion.

---

## 5. Secrets-hantering

### Principen (per D3, D4)

```
SecretsResolver.get_many(project_id, adapter.secrets_required)
    │
    ▼
dict[str, str]  ← EXAKT de nycklar adaptern deklarerat, inget mer
    │
    ▼
SandboxRunner.run(secrets=...)
    │
    ▼
Sandbox: injicera som env-vars i sandboxed process
    │
    ▼
SandboxResult: stdout/stderr REDACTADE innan loggning
```

### Redaktion

```python
def _redact_secrets(text: str, secrets: dict[str, str]) -> str:
    """Ersätt secret-värden med [REDACTED:KEY] i log-output."""
    for key, value in secrets.items():
        if value and len(value) > 4:
            text = text.replace(value, f"[REDACTED:{key}]")
    return text
```

Redaktion sker I `E2BSandboxRunner` innan `SandboxResult` konstrueras (se OQ-9).

---

## 6. Test-strategi

### 6.1 Unit-tests (mock E2B — inga externa beroenden)

```python
# tests/unit/test_e2b_runner.py

class MockE2BSandbox:
    """Test-double för E2B Sandbox."""

    def __init__(
        self,
        exit_code: int = 0,
        stdout: str = "PASS",
        stderr: str = "",
        network_calls: list[str] | None = None,
    ):
        self._exit_code = exit_code
        self._stdout = stdout
        self._stderr = stderr
        self._network_calls = network_calls or []

    async def filesystem_write(self, path: str, content: str) -> None: ...

    async def process_start(self, cmd: str, env_vars: dict, **kwargs) -> "MockProcess":
        return MockProcess(self._exit_code, self._stdout, self._stderr)

    async def close(self) -> None: ...

    async def get_connections(self) -> list[str]:
        return self._network_calls


@pytest.mark.asyncio
async def test_run_success(monkeypatch):
    monkeypatch.setattr("e2b.Sandbox.create", AsyncMock(return_value=MockE2BSandbox()))
    runner = E2BSandboxRunner(api_key="test-key", project_id=uuid4())
    result = await runner.run(
        code="print('PASS')", secrets={}, network_policy="none", timeout_ms=5000
    )
    assert result.success is True
    assert result.exit_code == 0
    assert result.network_calls == []
    assert result.duration_ms >= 0


@pytest.mark.asyncio
async def test_network_call_propagated(monkeypatch):
    sandbox = MockE2BSandbox(network_calls=["https://evil.example.com"])
    monkeypatch.setattr("e2b.Sandbox.create", AsyncMock(return_value=sandbox))
    runner = E2BSandboxRunner(api_key="test-key", project_id=uuid4())
    result = await runner.run(code="...", secrets={}, network_policy="none")
    # EngineerAgent abortar om network_calls != [] med network_policy="none"
    assert result.network_calls == ["https://evil.example.com"]


@pytest.mark.asyncio
async def test_secrets_redacted_in_output(monkeypatch):
    sandbox = MockE2BSandbox(stdout="key value is secret-value-123 done")
    monkeypatch.setattr("e2b.Sandbox.create", AsyncMock(return_value=sandbox))
    runner = E2BSandboxRunner(api_key="test-key", project_id=uuid4())
    result = await runner.run(
        code="...",
        secrets={"MY_KEY": "secret-value-123"},
        network_policy="none",
    )
    assert "secret-value-123" not in result.stdout
    assert "[REDACTED:MY_KEY]" in result.stdout


@pytest.mark.asyncio
async def test_rate_limit_triggers_fallback(monkeypatch):
    from e2b.exceptions import RateLimitError
    monkeypatch.setattr(
        "e2b.Sandbox.create", AsyncMock(side_effect=RateLimitError("429"))
    )
    mock_codespaces = AsyncMock(
        return_value=SandboxResult(
            success=True, stdout="PASS", stderr="", exit_code=0,
            duration_ms=500, network_calls=[]
        )
    )
    codespaces_runner = MagicMock(spec=CodespacesSandboxRunner)
    codespaces_runner.run = mock_codespaces

    e2b_runner = E2BSandboxRunner(api_key="test-key", project_id=uuid4())
    result = await run_with_fallback(
        code="print('PASS')", secrets={}, network_policy="none", timeout_ms=5000,
        runners=[e2b_runner, codespaces_runner],
    )
    assert result.success is True
    mock_codespaces.assert_called_once()
```

### 6.2 Integration-tests (mot riktig E2B free tier)

```python
# tests/integration/test_e2b_sandbox_real.py
# Körs INTE vid varje PR — se CI-konfiguration nedan

@pytest.mark.integration
@pytest.mark.slow
async def test_network_none_actually_blocks():
    """Verifierar att network_policy='none' faktiskt blockerar utgående anrop."""
    runner = E2BSandboxRunner(
        api_key=os.environ["E2B_API_KEY"],
        project_id=uuid4(),
    )
    attempt_network_code = """
import asyncio, httpx
async def main():
    try:
        r = await httpx.AsyncClient().get("https://httpbin.org/get", timeout=3.0)
        print(f"NETWORK_REACHED: {r.status_code}")
    except Exception as e:
        print(f"NETWORK_BLOCKED: {type(e).__name__}")
asyncio.run(main())
"""
    result = await runner.run(
        code=attempt_network_code,
        secrets={},
        network_policy="none",
        timeout_ms=15000,
    )
    assert "NETWORK_REACHED" not in result.stdout, (
        "SÄKERHETSFEL: network=none blockerade INTE nätverksanropet! "
        f"stdout: {result.stdout}"
    )
```

**CI rate-limit-skydd:**

```yaml
# Referens: .github/workflows/sandbox-integration.yml
jobs:
  sandbox-integration:
    # Kör BARA vid manuell trigger eller nattlig schemalagd körning
    # ALDRIG vid varje PR-push — skyddar E2B free tier-budget
    if: >
      github.event_name == 'workflow_dispatch' ||
      github.event_name == 'schedule'
    steps:
      - run: pytest tests/integration/ -m "integration" --timeout=120
    env:
      E2B_API_KEY: ${{ secrets.E2B_API_KEY }}
```

---

## 7. Konfiguration

```toml
# packages/sandbox/config.toml

[sandbox]
default_backend = "e2b"
fallback_order = ["e2b", "codespaces"]
# "local" ingår ALDRIG i fallback_order — kräver --unsafe-local explicit

[e2b]
template = "base"
connection_timeout_ms = 10000
max_daily_runs_soft_limit = 50   # Loggar WARNING vid 80% (40 körningar)

[codespaces]
machine_type = "basicLinux32gb"
auto_delete_timeout_minutes = 10

[security]
redact_secrets_in_logs = true
abort_on_unexpected_network_calls = true
# Om true: EngineerAgent abortar utan retry om network_calls != [] med policy=none
```

---

## 8. Öppna designfrågor (för Lead Architect att besluta)

| # | Fråga | Konsekvens om fel beslut | Rekommendation |
|---|---|---|---|
| OQ-6 | Vilken E2B SDK-version och vilket template har garanterad network=none-isolering? | Om network=none inte fungerar i vald version är R1 INTE mitigerad — Fas 3 DoD kan inte godkännas | Kräv integrationstestverifiering (test_network_none_actually_blocks) INNAN Fas 3-DoD signeras |
| OQ-7 | Ska `CodespacesSandboxRunner` implementeras fullt i Fas 3 eller bara stubba interfacet med tydligt felmeddelande? | Om E2B har downtime och Codespaces saknar implementation stoppas Engineer-loopen helt | Rekommendation: minst fungerande stub med `NotImplementedError("Codespaces fallback ej implementerad — kontakta operatör")` |
| OQ-8 | Finns `sandbox.network.get_connections()` i E2B free tier SDK? | Om ej tillgänglig faller vi tillbaka på regex-scan av output — svagare R1-garanti | Verifiera i E2B SDK-källkod/docs INNAN Fas 3 implementation startar |
| OQ-9 | Ska secrets-redaktion ske i `SandboxRunner.run()` eller i `EngineerAgent` innan loggning? | Om båda ställen redactar kan dubbel-redaktion ge `[REDACTED:[REDACTED:KEY]]` i logs | Rekommendation: redaktion sker EN gång i `E2BSandboxRunner` innan `SandboxResult` returneras |
