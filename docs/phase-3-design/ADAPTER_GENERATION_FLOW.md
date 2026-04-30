# ADAPTER_GENERATION_FLOW — Fas 3 Design

> Draft av Architect-draft (Sonnet). Review av Lead Architect (Opus) krävs innan Fas 3 öppnas.
> Datum: 2026-04-29. End-to-end-sekvensdiagram från `doc_url` till `adapter:registered`-event.
> Se ENGINEER_AGENT_SPEC.md och SANDBOX_INTEGRATION.md för detaljspec per komponent.

---

## 1. Komponent-legend

| Aktör / Komponent | Beskrivning |
|---|---|
| **Operator** | Människa (human-robin) som triggar och godkänner |
| **CLI / UI** | `python -m alchemy` (Fas 3) eller webb-UI (Fas 6) |
| **EngineerAgent** | `packages/agents/engineer/__init__.py` |
| **LiteLLM + Instructor** | LLM-lager, structured output via Instructor mot `AdapterDraft` |
| **E2BSandboxRunner** | `packages/sandbox/e2b_runner.py` — cloud-isolerad container |
| **FileSystem** | Lokal disk: `adapters/_generated/` (staging) och `adapters/` (aktiv) |
| **Lake** | Postgres + JSONB: `adapter_manifests`, `project_adapters`, `tool_calls_log`, `cost_ledger`, `events` |
| **WebSocket** | Gateway broadcast på topic `project:<id>` |

---

## 2. Huvud-sekvensdiagram

```mermaid
sequenceDiagram
    autonumber
    actor Operator
    participant CLI as CLI / UI
    participant EA as EngineerAgent
    participant LLM as LiteLLM + Instructor
    participant SB as E2BSandboxRunner
    participant FS as FileSystem
    participant Lake as Lake (Postgres)
    participant WS as WebSocket

    %% ── TRIGGER ─────────────────────────────────────────────────────────
    Operator->>CLI: python -m alchemy ingest <doc_url> --name <api_name>
    CLI->>EA: loop({doc_url, api_name, project_id})

    %% ── STEG 1: Hämta dokumentation ─────────────────────────────────────
    EA->>EA: tool_call: read_doc(url)
    EA-->>EA: httpx.AsyncClient().get(doc_url)
    Note over EA: Playwright-fallback om JS-rendered (body < 500 tecken)
    EA->>Lake: INSERT tool_calls_log {tool:"read_doc", url, content_length, used_playwright, ts}

    alt doc_fetch misslyckas efter 3 försök
        EA->>Lake: INSERT events {type:"adapter:fetch_failed", project_id, payload:{url}, ts}
        EA->>WS: EMIT adapter:fetch_failed
        EA-->>CLI: AgentResult(success=False, reason="doc_fetch_failed")
        Note over EA,CLI: STOP — eskalera till Operator
    end

    %% ── STEG 2: LLM-extraktion → AdapterDraft ───────────────────────────
    EA->>LLM: complete(doc_text, response_model=AdapterDraft)
    LLM-->>EA: AdapterDraft {api_name, base_url, endpoints, secrets_required, llm_confidence}
    EA->>Lake: INSERT tool_calls_log {tool:"write_pydantic_model", prompt_hash, ts}
    EA->>Lake: INSERT cost_ledger {agent_id:"engineer", model, tokens_in, tokens_out, cost_usd, ts}
    Note over EA,Lake: Cost-cap check: SELECT SUM(cost_usd) WHERE run_id=current

    %% ── STEG 3-4: Generera och skriv kod ────────────────────────────────
    EA->>LLM: complete(AdapterDraft → generera Python-kodsträngar)
    LLM-->>EA: {adapter.py, {api_name}_model.py, adapter_test.py}
    EA->>EA: ast.parse() syntaxvalidering på alla 3 filer
    EA->>FS: WRITE adapters/_generated/{api_name}/v1/
    Note over FS: 4 filer + manifest.json med status="generated"
    EA->>Lake: INSERT tool_calls_log {tool:"write_adapter", files_written:4, ts}
    EA->>Lake: INSERT cost_ledger {cost_usd, ts}

    %% ── STEG 5: Sandbox-körning ──────────────────────────────────────────
    EA->>SB: run(adapter_test.py, secrets={mock}, network_policy="none", timeout_ms=60000)
    SB->>SB: Sandbox.create(template="base", metadata={project_id, purpose:"adapter_test"})
    SB->>SB: filesystem.write("/home/user/adapter_test.py")
    SB->>SB: process.start("python adapter_test.py", env_vars={mock_secrets})
    SB-->>EA: SandboxResult {success, stdout, stderr, exit_code, duration_ms, network_calls}
    EA->>Lake: INSERT tool_calls_log {tool:"sandbox_test", exit_code, network_calls_count, ts}

    alt network_calls != [] AND network_policy="none"
        EA->>Lake: INSERT events {type:"adapter:security_violation", project_id, payload:{network_calls}, ts}
        EA->>WS: EMIT adapter:security_violation {api_name, network_calls}
        EA-->>CLI: AgentResult(success=False, reason="network_policy_violated")
        Note over EA,CLI: ABORT utan retry — potentiell prompt-injection
    else exit_code != 0 ELLER "PASS" ej i stdout
        Note over EA: Retry-loop (max 3 försök per ENGINEER_AGENT_SPEC.md steg 5)
        EA->>LLM: complete(stderr + draft → fix code)
        EA->>Lake: INSERT cost_ledger {cost_usd, ts}
        Note over EA,Lake: Cost-cap check vid varje retry
        EA->>SB: run(fixed_test.py, ...) [retry]
        Note over EA: Efter 3 misslyckanden: emit sandbox_max_retries, STOP
    else success=True AND exit_code=0 AND "PASS" i stdout
        EA->>FS: UPDATE manifest.json → status="sandbox_passed"
        EA->>Lake: UPDATE adapter_manifests SET status="sandbox_passed" WHERE name AND version
        EA->>Lake: INSERT events {type:"adapter:sandbox_passed", project_id, payload:{api_name, manifest_path}, ts}
        EA->>WS: EMIT adapter:sandbox_passed {api_name, manifest_path, ts}
    end

    %% ── STEG 6: Human-in-the-loop ────────────────────────────────────────
    WS-->>CLI: adapter:sandbox_passed event
    CLI->>Operator: Visa manifest-diff + kod-preview + sandbox stdout/stderr + secrets_required
    Note over Operator,CLI: AGENT IDLE — ingen aktiv loop, väntar på operator

    alt Operator godkänner
        Operator->>CLI: python -m alchemy adapter approve {api_name}
        CLI->>EA: approve({api_name, project_id})
    else Operator avvisar
        Operator->>CLI: python -m alchemy adapter reject {api_name} --reason "..."
        CLI->>EA: reject({api_name, reason})
        EA->>Lake: UPDATE adapter_manifests SET status="rejected"
        EA->>Lake: INSERT events {type:"adapter:rejected", project_id, payload:{api_name, reason}, ts}
        EA->>WS: EMIT adapter:rejected {api_name, reason}
        EA-->>CLI: AgentResult(success=False, reason="operator_rejected")
        Note over EA,FS: Staging-katalog _generated/ behålls för felsökning
    end

    %% ── STEG 7: Promotering och registrering ─────────────────────────────
    EA->>FS: COPY adapters/_generated/{api_name}/v1/ → adapters/{api_name}/v1/
    EA->>FS: UPDATE manifest.json → status="human_approved"
    EA->>Lake: tool_call: register_adapter({api_name, version:"v1", project_id})
    EA->>Lake: INSERT adapter_manifests {name, version, schema_hash, doc_url, generated_at,<br/>model_used, prompts_used, secrets_required, status:"human_approved"}
    EA->>Lake: INSERT project_adapters {project_id, adapter_name, adapter_version:"v1", pinned_at}
    EA->>Lake: INSERT tool_calls_log {tool:"register_adapter", manifest_id, ts}
    EA->>Lake: INSERT events {type:"adapter:registered", project_id, payload:{api_name, version:"v1"}, ts}

    %% ── STEG 8: Final broadcast ───────────────────────────────────────────
    EA->>WS: EMIT adapter:registered {api_name, version:"v1", manifest_path, ts}
    WS-->>CLI: adapter:registered event
    EA-->>CLI: AgentResult(success=True, output:{adapter_name, version, retries_used, cost_usd})
    CLI->>Operator: "Adapter {api_name} v1 registrerad och aktiv"
```

---

## 3. Events emitterade (kronologisk ordning)

| # | Event-typ | Topic | Trigger | Payload-nycklar |
|---|---|---|---|---|
| 1 | `adapter:fetch_failed` | `project:{id}` | read_doc misslyckas 3 gånger | `{url, attempt_count}` |
| 2 | `adapter:security_violation` | `project:{id}` | `network_calls != []` med `policy=none` | `{api_name, network_calls}` |
| 3 | `adapter:sandbox_passed` | `project:{id}` | exit_code=0 och "PASS" i stdout | `{api_name, manifest_path, sandbox_duration_ms}` |
| 4 | `adapter:rejected` | `project:{id}` | Operator kör `reject` | `{api_name, reason}` |
| 5 | `adapter:registered` | `project:{id}` | register_adapter slutförd | `{api_name, version, manifest_path}` |
| — | `adapter:cost_cap_hit` | `project:{id}` | `spent_usd >= cost_cap_usd` | `{api_name, spent_usd, cap_usd}` |
| — | `adapter:sandbox_max_retries` | `project:{id}` | 3 sandbox-fail | `{api_name, last_stderr, retries: 3}` |

Alla events skrivs till Lake `events`-tabellen (immutable append) med fälten:
```json
{
  "type": "adapter:registered",
  "project_id": "uuid-redacted",
  "payload": {"api_name": "open_meteo_forecast", "version": "v1", "manifest_path": "adapters/open_meteo_forecast/v1/manifest.json"},
  "ts": "2026-04-29T12:05:00Z"
}
```

---

## 4. Lake-tabeller skrivna/lästa

| Tabell | Operation | Steg | Nyckelkolumner |
|---|---|---|---|
| `tool_calls_log` | INSERT | 1, 2, 3, 5, 7 | `tool, input_hash, output_hash, cost_usd, ts, run_id` |
| `cost_ledger` | INSERT | 2, 3, retry | `project_id, agent_id:"engineer", model, tokens_in, tokens_out, cost_usd, ts` |
| `cost_ledger` | SELECT SUM | Före varje LLM-anrop | `WHERE run_id = current_run_id` — cost-cap guard |
| `adapter_manifests` | INSERT/UPDATE | 5 (sandbox_passed), 7 | `name, version, schema_hash, doc_url, generated_at, model_used, prompts_used, secrets_required, status` |
| `project_adapters` | INSERT | 7 | `project_id, adapter_name, adapter_version, pinned_at` |
| `events` | INSERT | Alla nyckel-händelser | `type, project_id, payload JSONB, ts` |
| `discovery_index` | READ (valfritt) | Pre-trigger (Fas 4) | `discovery_id, doc_url, api_name` — om Scout triggar Engineer |

---

## 5. Operator-godkännande: status-transition

```
  [loop() anropas]
        │
        ▼
   GENERATED ──► [ABORT: fetch_fail / cost_cap]
        │
        │  sandbox_test
        ▼
  ┌─────────────────────────────────────┐
  │ network_calls != [] → ABORT (R1)    │
  │ exit_code != 0 → retry (max 3)      │
  │ 3 retries → ABORT (sandbox_max)     │
  └──────────────┬──────────────────────┘
                 │ success=True, network_calls=[]
                 ▼
         SANDBOX_PASSED
                 │
                 │  WebSocket → Operator granskar preview
                 │  [AGENT IDLE — ingen aktiv loop]
                 │
         ┌───────┴────────┐
    [approve]         [reject]
         │                │
         ▼                ▼
  HUMAN_APPROVED      rejected
         │
         │  register_adapter (Lake + FS)
         ▼
        ACTIVE
         │
         │  (framtida Self-Repair eller manuellt)
         ▼
      DEPRECATED
```

**Human-in-the-loop position**: Övergången `SANDBOX_PASSED → HUMAN_APPROVED` kräver
explicit operator-aktion. Ingen timeout. Adaptern gör ALDRIG nätverksanrop mot riktig
API utan operatörens godkännande (per D4, ARCHITECTURE.md sektion 8, R1-mitigering).

---

## 6. Felvägar och eskaleringsmatris

| Felscenario | Adapter-status | Retry? | Operator-aktion krävs | Event |
|---|---|---|---|---|
| `doc_url` svarar ej (3 försök) | `GENERATED` (abort) | Nej | Ny URL eller manuell fetch | `adapter:fetch_failed` |
| Security violation (`network_calls != []`) | `GENERATED` (abort) | Nej | Granska genererad kod — möjlig prompt-injection | `adapter:security_violation` |
| Sandbox fail, max 3 retries | `GENERATED` (abort) | Uttömt | Manuell felsökning av stderr-log | `adapter:sandbox_max_retries` |
| Cost cap $5 nådd | `GENERATED` (abort) | Nej | Höj cap i config eller granska prompt-kvalitet | `adapter:cost_cap_hit` |
| Operator avvisar | `rejected` | Nej (ny run krävs) | Operatören har agerat — ny `loop()` vid behov | `adapter:rejected` |
| E2B rate-limit / downtime | N/A | Auto-fallback | Nej (om Codespaces ok) | — |
| Alla sandbox-backends fail | `GENERATED` (abort) | Nej | Kontrollera E2B + Codespaces status | `adapter:sandbox_max_retries` |

---

## 7. Koppling till andra system-loops

**Loop 1 — Self-discovering (Fas 4):**
Scout-agenten subscribe:ar på `adapter:registered` och uppdaterar sin ranking i
`discovery_index`. Scout emitterar `discovery:top_n_ready` → EngineerAgent kan
auto-triggas med `{doc_url, api_name}` från `discovery_index`. Flödet ovan är identiskt
oavsett trigger-källa (Operator direkt vs Scout).

**Loop 3 — Self-evaluating (Fas 5):**
`adapter:registered`-eventet (steg 8) → Judge-agenten subscribe:ar och startar
automatiskt benchmark → skriver till `arena_scores` → WebSocket uppdaterar leaderboard
→ Scout läser `arena_scores` för bättre framtida ranking. Compounding-effekt aktiveras.
