# ENGINEER_AGENT_SPEC — Fas 3 Design

> Draft av Architect-draft (Sonnet). Review av Lead Architect (Opus) krävs innan Fas 3 öppnas.
> Datum: 2026-04-29. Baserat på ARCHITECTURE.md Loop 2, DECISIONS.md D3/D4/D7, RISK_REGISTER.md R1/R4/R11.

---

## 1. Klass-deklaration

```python
class EngineerAgent(BaseAgent):
    name: str = "engineer"
    role: Role = Role.EXECUTOR
    tool_allowlist: list[str] = [
        "read_doc",
        "write_pydantic_model",
        "write_adapter",
        "sandbox_test",
        "register_adapter",
    ]
    model: str  # Läses från packages/agents/engineer/config.toml — ALDRIG hårdkodat
```

Konfigurationsfil: `packages/agents/engineer/config.toml`

```toml
[agent]
model = "claude-sonnet-4-6"
max_retries = 3
cost_cap_usd = 5.0
doc_fetch_timeout_ms = 15000
sandbox_timeout_ms = 60000
playwright_fallback = true
min_llm_confidence = 0.6

[prompts]
system = "Du är en precis API-analysator. Extrahera exakt vad som finns i dokumentationen. Uppfinn ingenting."
# Prompt-texter lagras HÄR, inte i koden (per D7 reproducibility)
# Prompt-hash loggas per anrop för replay
```

---

## 2. Input-kontrakt

```python
class EngineerInput(BaseModel):
    doc_url: str                         # URL till API-dokumentation
    api_name: str                        # Slug-namn, t.ex. "open_meteo_forecast"
    project_id: UUID
    discovery_id: UUID | None = None     # Om triggas av Scout (Fas 4)
    secrets_hint: list[str] = []         # Nyckelnamn operatören redan vet om
    force_regen: bool = False            # Om True: regenerera även om adapter finns
```

Input levereras via `BaseAgent.loop(input_data: dict[str, Any])` och valideras med
`EngineerInput.model_validate(input_data)` vid loop-start.

---

## 3. Intermediär Pydantic-modell: AdapterDraft

Instructor-structured output mot denna modell i Steg 2:

```python
class EndpointSpec(BaseModel):
    path: str                            # t.ex. "/v1/forecast"
    method: str                          # "GET" | "POST"
    query_params: list[str]              # Parameternamn
    response_fields: dict[str, str]      # fältnamn -> Python-typ (sträng, t.ex. "float")
    requires_auth: bool
    auth_header: str | None              # t.ex. "Authorization: Bearer {key}"

class AdapterDraft(BaseModel):
    api_name: str
    base_url: str
    endpoints: list[EndpointSpec]
    secrets_required: list[str]          # Exakta env-var-namn, INGA wildcards
    rate_limit_hint: str | None          # t.ex. "100 req/min"
    doc_url: str
    llm_confidence: float                # 0.0–1.0, Instructor extrakt
```

---

## 4. Steps (huvud-loop)

### Steg 1 — Hämta dokumentation (`read_doc`)

1. Försök med `httpx.AsyncClient` (timeout: `doc_fetch_timeout_ms` = 15 000 ms).
2. Kontrollera response: om HTML-body innehåller `<noscript>` eller body-längd < 500 tecken
   (indikator på JS-rendered sida) — eskalera till Playwright headless-fetch.
3. Playwright aktiveras ENDAST som fallback, aldrig som default, för att undvika onödig
   overhead och beroende av `playwright`-skill per PHASE_PLAN.md Fas 3.
4. Extrahera ren text: strip HTML-tags, bevara kodblock (` ``` `), tabeller, rubriker.
5. Logga till `tool_calls_log`:
   ```json
   {
     "tool": "read_doc",
     "url": "https://example.com/api/docs",
     "content_length": 4200,
     "used_playwright": false,
     "ts": "2026-04-29T12:00:00Z"
   }
   ```

**Failure-mode**: URL svarar inte efter 3 försök (exponential backoff: 1s, 2s, 4s)
→ `AgentResult(success=False, output={"reason": "doc_fetch_failed", "url": doc_url})`
→ Eskalera till operator via WebSocket-event `adapter:fetch_failed`.

---

### Steg 2 — Extrahera struktur via LLM (`write_pydantic_model`)

1. Anropa `complete()` via LiteLLM-wrapper med Instructor-patch mot `AdapterDraft`.
2. Prompt-innehåll (texter från `config.toml [prompts]`):
   - Systemroll: "Du är en precis API-analysator. Extrahera exakt vad som finns i
     dokumentationen. Uppfinn ingenting."
   - Dokumentationstext (trunkeras till ~40 000 tokens om längre; vid trunkering loggas
     `truncated: true` i `tool_calls_log`).
   - Instruktion: "Lista EXAKT de nyckelnamn i `secrets_required` som API:et kräver.
     Inga wildcards. Inga antaganden utöver vad dokumentationen explicit anger."
3. Validera `AdapterDraft` via Instructor. Om `llm_confidence < 0.6` → logga WARNING i
   agent-log och flagga `manifest.json` med `low_confidence: true`.
4. Logga prompt-hash till `tool_calls_log` (per D7 reproducibility — samma prompt + seed
   ska ge byte-identisk `AdapterDraft`).

**Failure-mode**: Instructor kan inte parsa structured output efter 2 interna retries
→ räknas som ett retry i den yttre retry-loopen (se Steg 5 retry-logic).

---

### Steg 3 — Generera kod-strängar (`write_adapter`)

Producera tre Python-strängar. Kod genereras som Python-strängar av LLM och valideras
syntaktisk med `ast.parse()` innan filskrivning.

**3a. Pydantic-modell** (`{api_name}_model.py`):
```python
# Genererat av EngineerAgent {ts} — REDIGERA INTE MANUELLT
# schema_hash: {sha256_of_draft}
from pydantic import BaseModel

class {ApiName}Record(BaseModel):
    # Fält extraherade från AdapterDraft.endpoints[*].response_fields
    # Varje fält har Python-typ direkt från EndpointSpec.response_fields
    field_name: field_type
    ...
```

**3b. Adapter-klass** (`adapter.py`):
```python
# Genererat av EngineerAgent {ts}
import httpx
from datetime import datetime, timezone
from packages.interfaces import BaseAdapter, Record, AdapterManifest, SecretsResolver
from .{api_name}_model import {ApiName}Record

class {ApiName}Adapter(BaseAdapter):
    name = "{api_name}"
    version = "v1"
    schema_hash = "{sha256_of_draft}"
    secrets_required = {draft.secrets_required!r}

    async def fetch(self, query, secrets):
        key = await secrets.get(query["project_id"], "{secret_key}")
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "{base_url}{path}",
                headers={"{auth_header_key}": f"Bearer {key}"},
                params={p: query.get(p) for p in {draft.endpoints[0].query_params!r}},
            )
            resp.raise_for_status()
            for item in resp.json().get("data", [resp.json()]):
                yield Record(
                    project_id=query["project_id"],
                    adapter_name=self.name,
                    adapter_version=self.version,
                    schema_hash=self.schema_hash,
                    payload={ApiName}Record(**item).model_dump(),
                    fetched_at=datetime.now(timezone.utc),
                )

    def manifest(self) -> AdapterManifest:
        return AdapterManifest(
            name=self.name,
            version=self.version,
            schema_hash=self.schema_hash,
            doc_url="{doc_url}",
            generated_at=datetime.now(timezone.utc),
            model_used="{model_from_config}",
            prompts_used=["{prompt_hash}"],
            secrets_required=self.secrets_required,
        )
```

**3c. Minimaltest** (`adapter_test.py`):
```python
# Kör mot mock-data — INGA riktiga nätverksanrop
# Avsedd för SandboxRunner med network_policy="none"
import asyncio, json
from unittest.mock import AsyncMock, patch

MOCK_RESPONSE = {json.dumps(mock_payload_from_draft)}  # Syntetisk baserat på schema

async def test_adapter():
    from adapter import {ApiName}Adapter
    adapter = {ApiName}Adapter()

    class MockSecrets:
        async def get(self, project_id, key):
            return "mock-key-value"

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=type("R", (), {
                "json": lambda self: MOCK_RESPONSE,
                "raise_for_status": lambda self: None,
            })()
        )
        records = [r async for r in adapter.fetch(
            {"project_id": "00000000-0000-0000-0000-000000000001"},
            MockSecrets(),
        )]

    assert len(records) >= 1, f"Förväntade minst 1 record, fick {len(records)}"
    assert records[0].adapter_name == "{api_name}", "Fel adapter_name"
    assert records[0].adapter_version == "v1", "Fel version"
    print("PASS")

asyncio.run(test_adapter())
```

`schema_hash` beräknas som `sha256(json.dumps(AdapterDraft.model_dump(), sort_keys=True))`.
`ast.parse()` valideras på alla tre kodsträngar innan filskrivning — syntaxfel eskalerar
omedelbart till retry utan att slösa på sandbox-körning.

---

### Steg 4 — Skriv till staging-katalog

Skriv kod-filerna till `adapters/_generated/{api_name}/v1/`:

```
adapters/_generated/{api_name}/v1/
  __init__.py           (tom, markerar paketet)
  adapter.py            (adapter-klassen)
  {api_name}_model.py   (Pydantic-modellen)
  adapter_test.py       (minitest)
  manifest.json         (status: "generated")
```

`manifest.json` vid detta steg:
```json
{
  "name": "{api_name}",
  "version": "v1",
  "schema_hash": "{sha256}",
  "doc_url": "https://example.com/api/docs",
  "generated_at": "2026-04-29T12:00:00Z",
  "model_used": "claude-sonnet-4-6",
  "prompts_used": ["{prompt_hash_sha256}"],
  "secrets_required": ["API_KEY_NAME"],
  "status": "generated",
  "low_confidence": false
}
```

---

### Steg 5 — Kör sandbox (`sandbox_test`)

1. Läs `adapter_test.py` från staging-katalog.
2. Anropa:
   ```python
   result = await sandbox_runner.run(
       code=adapter_test_py_content,
       secrets={"mock-key-value": "mock"},  # Aldrig riktiga keys i sandbox
       network_policy="none",
       timeout_ms=sandbox_timeout_ms,  # 60 000 ms
   )
   ```
3. Validera:
   - `result.success == True` och `result.exit_code == 0`
   - `result.stdout` innehåller "PASS"
   - `result.network_calls == []` (R1-enforcement: network=none)
4. Om `result.network_calls` inte är tom → logga SECURITY WARNING, abort utan retry,
   eskalera till operator (potentiell prompt-injection i genererad kod).

**Retry-logic (per R4, max 3 försök):**

| Försök | Strategi |
|--------|---------|
| Retry 1 | Skicka `stderr` + original `AdapterDraft` till LLM: "Fix detta specifika fel: {stderr}. Generera ny adapter.py och adapter_test.py." |
| Retry 2 | Skicka original `doc_text` + ackumulerade `stderr`-loggar, be om komplett regenerering från grunden. |
| Retry 3 | Som retry 2 men med `temperature=0` för deterministisk output. |
| Max retries nådd | `AgentResult(success=False, reason="sandbox_max_retries", last_stderr=...)` → eskalera till operator |

**Cost-cap enforcement per försök:**
```
Före varje LLM-anrop:
  spent = SELECT SUM(cost_usd) FROM cost_ledger WHERE run_id = current_run_id
  IF spent >= cost_cap_usd ($5.00):
    ABORT → AgentResult(success=False, reason="cost_cap_hit", spent_usd=spent)
    EMIT WebSocket: "adapter:cost_cap_hit"
```

---

### Steg 6 — Human-in-the-loop (`human_approved`)

Efter sandbox_passed:

1. Uppdatera `manifest.json` → `"status": "sandbox_passed"`.
2. Skriv till Lake `adapter_manifests` med status `SANDBOX_PASSED`.
3. Emit WebSocket-event på `project:{project_id}`:
   ```json
   {
     "type": "adapter:sandbox_passed",
     "api_name": "{api_name}",
     "version": "v1",
     "manifest_path": "adapters/_generated/{api_name}/v1/manifest.json",
     "ts": "2026-04-29T12:01:00Z"
   }
   ```
4. UI (Fas 3: CLI; Fas 6: webb-UI) visar:
   - Manifest-diff (vad som ändrats sedan sist, eller ny adapter)
   - Genererad kod-preview (adapter.py + model.py)
   - Sandbox stdout/stderr
   - `secrets_required`-lista för operator-verifiering
5. Vänta på operator-svar (agent i IDLE, ingen aktiv loop):
   - **Godkänn** (Fas 3 CLI): `python -m alchemy approve {api_name}`
   - **Avvisa**: `python -m alchemy reject {api_name} --reason "..."` → status `rejected`
   - **Fas 6 UI**: knapp "Aktivera adapter" → POST `/api/adapters/{api_name}/approve`
6. Ingen timeout — agent väntar indefinitely. Operator ansvarar för att agera.

---

### Steg 7 — Promovera och registrera (`register_adapter`)

1. Kopiera `adapters/_generated/{api_name}/v1/` → `adapters/{api_name}/v1/`.
2. Uppdatera `manifest.json` → `"status": "human_approved"`.
3. Skriv/uppdatera rad i Lake `adapter_manifests`:
   ```sql
   INSERT INTO adapter_manifests (name, version, schema_hash, doc_url, generated_at,
     model_used, prompts_used, secrets_required, status)
   VALUES (...)
   ON CONFLICT (name, version) DO UPDATE SET status = EXCLUDED.status;
   ```
4. Länka i `project_adapters`:
   ```sql
   INSERT INTO project_adapters (project_id, adapter_name, adapter_version, pinned_at)
   VALUES ({project_id}, '{api_name}', 'v1', NOW());
   ```
5. Emit WebSocket-event: `adapter:registered` på `project:{project_id}`.

---

### Steg 8 — Returnera AgentResult

```python
return AgentResult(
    agent_name="engineer",
    success=True,
    output={
        "adapter_name": api_name,
        "version": "v1",
        "manifest_path": f"adapters/{api_name}/v1/manifest.json",
        "retries_used": retry_count,
        "llm_confidence": draft.llm_confidence,
    },
    tool_calls_made=["read_doc", "write_pydantic_model", "write_adapter",
                     "sandbox_test", "register_adapter"],
    cost_usd=total_cost_from_ledger,
    duration_ms=elapsed_ms,
)
```

---

## 5. Tool-allowlist (detaljerad)

| Tool-namn | Input | Output | Sidoeffekter |
|---|---|---|---|
| `read_doc` | `{url: str, use_playwright: bool}` | `{content: str, content_length: int, used_playwright: bool}` | Utgående nätverksanrop (tillåtet för agent, ej för adapter-kod) |
| `write_pydantic_model` | `{draft: AdapterDraft, output_dir: str}` | `{file_path: str, schema_hash: str}` | Skriver fil till `adapters/_generated/` |
| `write_adapter` | `{draft: AdapterDraft, output_dir: str}` | `{file_paths: list[str]}` | Skriver 3 filer + manifest.json |
| `sandbox_test` | `{test_file_path: str, secrets: dict[str,str], network_policy: str, timeout_ms: int}` | `SandboxResult` | E2B API-anrop (utgående från agent-process) |
| `register_adapter` | `{api_name: str, version: str, project_id: UUID, manifest_path: str}` | `{manifest_id: str, event_emitted: bool}` | Lake INSERT + WebSocket emit |

Varje tool-anrop loggas i `tool_calls_log` med:
```json
{
  "tool": "sandbox_test",
  "input_hash": "sha256-of-inputs",
  "output_hash": "sha256-of-SandboxResult",
  "cost_usd": 0.0,
  "ts": "2026-04-29T12:01:30Z",
  "run_id": "uuid-of-this-engineer-run"
}
```

---

## 6. Status-sekvens (AdapterStatus enum)

```
GENERATED
    │
    ▼ (sandbox_test kör)
SANDBOX_PASSED ──► (om network_calls != []) ──► ABORT + operator eskalering
    │
    ▼ (operator approve)
HUMAN_APPROVED
    │
    ▼ (register_adapter slutförd)
ACTIVE
    │
    ▼ (framtida Self-Repair eller manuellt)
DEPRECATED
```

Felvägar:
- Sandbox fail (max 3 retries) → `status` förblir `GENERATED`, `AgentResult.success=False`
- Operator reject → ny status `rejected` (lägg till i `AdapterStatus` enum — se OQ-5)
- Cost cap hit → abort, `status` förblir `GENERATED`

---

## 7. Fil- och katalogstruktur (leverabel)

```
packages/agents/engineer/
  __init__.py              (EngineerAgent-klass)
  config.toml              (model, caps, prompts)
  tools/
    read_doc.py            (httpx + Playwright-fallback)
    write_pydantic_model.py
    write_adapter.py
    sandbox_test.py        (delegerar till SandboxRunner)
    register_adapter.py    (Lake + WebSocket)

adapters/_generated/       (staging — ej commit:at per .gitignore)
adapters/{api_name}/v{n}/  (promoterad, commit:ad)
```

---

## 8. Öppna designfrågor (för Lead Architect att besluta)

| # | Fråga | Konsekvens om fel beslut | Rekommendation |
|---|---|---|---|
| OQ-1 | Instructor direkt mot Anthropic-klient eller via LiteLLM proxy? | LiteLLM-proxy ger cost-callback automatiskt; direktanrop kräver manuell cost-tracking | Rekommendation: LiteLLM proxy för att hålla cost_ledger konsistent |
| OQ-2 | `write_pydantic_model` och `write_adapter` — separata tool_calls eller kombinerat? | Separata ger retry-granularitet per steg; kombinerat är enklare | Rekommendation: separata (bättre observability) |
| OQ-3 | Sandbox skickar bara `adapter_test.py` eller hela katalogen? | Hela katalogen undviker import-problem; bara test-filen är minimalt | Rekommendation: hela katalogen (adapter.py + model.py + test) |
| OQ-4 | CLI-subcommand `alchemy approve` — ny subcommand eller flagga på `alchemy ingest`? | Ny subcommand är tydligare men kräver CLI-utökning | Rekommendation: ny subcommand `alchemy adapter approve/reject` |
| OQ-5 | `rejected` saknas i `AdapterStatus` enum i `interfaces/__init__.py` — lägg till nu eller i Fas 3? | Om ej tillagt i Fas 3-start kan enum-missmatch uppstå | Rekommendation: lägg till `REJECTED = "rejected"` i enum innan Fas 3 öppnas |
