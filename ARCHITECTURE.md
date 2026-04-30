# ARCHITECTURE — API Alchemy Engine

> Definitiv arkitekturskiss for Fas 0. Kompletterad med beslut fran DECISIONS.md.
> Datum: 2026-04-30. Planner: claude-opus-4.7. Skeptic-pushback applicerad (sektionen "Skeptic challenges" i slutet).

---

## 1. Lager-stack

```
+--------------------------------------------------------+
|  Frontend (Next.js + Tailwind + shadcn)                |  Fas 6
|  - Renderar UI fran tool_registry (action parity)      |
+----------------------+---------------------------------+
                       | WebSocket + REST
+----------------------v---------------------------------+
|  Gateway (FastAPI)                                     |  Fas 1
|  - Routing, localhost-only, NO logic                   |
|  - WebSocket broadcast pa topic project:<id>           |
+----------------------+---------------------------------+
                       |
+----------------------v---------------------------------+
|  Orchestrator                                          |  Fas 1
|  - Workflow-DSL (Python) komponerar atomic primitives  |
|  - Zero API-kunskap                                    |
+----------------------+---------------------------------+
                       |
+----------------------v---------------------------------+
|  Atomic primitives                                     |  Fas 1+
|  - Pure functions, Pydantic in/out                     |
|  - Each one is a tool_call in tool_registry            |
+----------------------+---------------------------------+
                       |
        +--------------+---------------+
        |                              |
+-------v-------+              +-------v-------+
| Adapters      |              | Agent runtime |  Fas 3+
| (registry)    |              | (Scout, Eng,  |
|               |              |  Judge, ...)  |
+-------+-------+              +-------+-------+
        |                              |
        | (validated I/O via Pydantic) |
        v                              v
+--------------------------------------------------------+
|  Data Lake (Postgres + JSONB)                          |  Fas 1
|  - projects, events (immutable), records (JSONB)       |
|  - agent_actions, tool_calls_log, arena_scores         |
|  - adapter_manifests, discovery_index, cost_ledger     |
|  - project_adapters (D2 pinning), audit_replay         |
+--------------------------------------------------------+
                       ^
                       |
+----------------------+---------------------------------+
|  LiteLLM-lager (alla LLM-anrop)                        |  Fas 1
|  - Instructor for structured output                    |
|  - cost-callback -> cost_ledger                        |
|  - Modellnamn endast i config                          |
+----------------------+---------------------------------+
                       |
+----------------------v---------------------------------+
|  Sandbox (E2B free tier default, Codespaces fallback)  |  Fas 3
|  - Auto-genererad adapter-kod kor HAR forst            |
|  - network=none default, opt-in per anrop              |
+--------------------------------------------------------+
```

Build-time roller (utanfor produkten): Lead Architect (Opus), Chief Skeptic (Opus), Senior Implementer (Sonnet sub-agent), Verifier (Sonnet sub-agent), Showcase Auditor (Opus). Se AGENT_ROLES.md.

## 2. Karnabstraktioner (definieras i packages/interfaces/__init__.py)

| Klass | Roll |
|---|---|
| BaseAdapter | Kontrakt for API-adaptrar. Falt: name, version, schema_hash, secrets_required, fetch(query) -> AsyncIterator[Record] |
| BaseAgent | Kontrakt for runtime-agenter. Falt: name, role, tool_allowlist, loop(input) -> AgentResult |
| BaseTool / ToolSpec | En atomic primitive. Falt: name, input_schema, output_schema, handler, agent_allowed, ui_component |
| ProjectState | Delat state-trad mellan UI och agent. Wraps Lake records + WebSocket-broadcast |
| SandboxRunner | Abstraktion over E2B / Codespaces / LocalProcess |
| SecretsResolver | Abstraktion over Doppler / LocalToml |
| ReplayCursor | Lasa historiska records taggade med specifik adapter_version |
| ToolRegistry | dict[str, ToolSpec] — single source of truth for action parity |

## 3. Tre self-loops konkret kopplade

### Loop 1: Self-discovering
1. Operator (eller agent) triggar discover(domain) primitive
2. Scout-agenten kor: web_search -> read_docs -> evaluate_api
3. Resultat skrivs till discovery_index (project_id-segmenterad)
4. Event emit: discovery:top_n_ready pa WebSocket-topic
5. Engineer-agenten subscribe:ar och kan trigga register_top_n

### Loop 2: Self-extending
1. Engineer tar discovery_id -> hamtar doc-URL
2. LLM-anrop (via LiteLLM + Instructor) -> Pydantic-modell + adapter-kod + minimal-test
3. Manifest skrivs: name, version, schema_hash, doc_url, generated_at, model_used, prompts_used
4. SandboxRunner kor adaptern mot mock-data (E2B, network=none)
5. Status: generated -> sandbox_passed -> (UI prompt) -> human_approved -> active
6. Manifest sparas i adapter_manifests; kod sparas i adapters/<name>/v<n>/
7. Event emit: adapter:registered

### Loop 3: Self-evaluating
1. Judge subscribe:ar adapter:registered
2. Kor benchmark: latens (p50/p95), datatathet (#falt/respons), kostnad/1000 anrop, DX-score
3. Skriver till arena_scores (taggat med adapter_version)
4. Frontend leaderboard subscribe:ar och uppdaterar live
5. Scout laser arena_scores for att rangordna kandidater i framtida discovery

Compounding-effekt: efter 50 adaptrar finns det data om vad som funkar inom domanen. Scout's framtida ranking blir battre an vid forsta korningen.

## 4. Action parity-mekanism (konkret)

Single source of truth: packages/orchestrator/primitives/_registry.py

```python
TOOL_REGISTRY: dict[str, ToolSpec] = {
    "ingest_url": ToolSpec(...),
    "infer_schema": ToolSpec(...),
    "generate_insights": ToolSpec(...),
}
```

Frontend-build importerar registret (codegen vid build-time eller runtime-fetch pa /api/tools) och renderar UI-komponenter fran ToolSpec.ui_component.

CI-test i tests/test_action_parity.py:
- Laser frontend-routes (Next.js manifest)
- Laser TOOL_REGISTRY
- Faller om en route saknar primitiv, eller en primitiv saknar UI-mapping nar agent_allowed=True och ui_visible=True

Konsekvens: en agent kan trigga vilken tool som helst som anvandaren har som en knapp. UI och agent ar i bisar parity per definition.

## 5. State-flode mellan UI och agent

```
operator klickar knapp -> POST /api/tools/<name> -> handler() -> Lake skrivning -> WebSocket emit -> frontend re-render

agent kor tool_call -> samma handler() -> samma Lake skrivning -> samma WebSocket emit -> frontend re-render
```

Ingen separat "agent memory". Agent prenumererar pa samma WebSocket som UI. UI prenumererar pa WebSocket. Samma state-trad.

## 6. Kostnadskontroll (cost_ledger)

LiteLLM-callback skriver till cost_ledger med falten: project_id, agent_id, model, tokens_in, tokens_out, cost_usd, ts. Per projekt finns:

- daily_cap_usd
- monthly_cap_usd
- current_spend_usd (rolling)

Cap-hit beteende:
- Vid 80% av cap: log warning, skicka WebSocket notification
- Vid 100% av cap: agent-loopar avslutas gracefully (ingen ny LLM-anrop), pagaende sandbox-korning fardigstalls, projekt parkeras i UI med "Cost cap reached. Increase or wait." Inga hard crash.

## 7. Reproducibility & Replay

- Varje tool_call loggar: prompt, model, temperature, seed, version, input_hash, output_hash, ts
- ReplayCursor(project_id, until_ts) ger en snapshot av records som existerade vid until_ts
- Adapter-version pinning gor att replay anvander exakt samma adapter-kod som producerade originaldatan
- Test: tests/integration/test_replay.py kor en sekvens, snapshot:ar, och replay:ar — output ska vara byte-identisk for deterministiska anrop

## 8. Sakerhetsmodell (sammanfattning)

- Sandbox isolerar all auto-genererad kod (E2B network=none default)
- secrets_required per adapter — sandbox far endast den specifika key, aldrig hela vault
- Human-in-the-loop pa adapter-aktivering (status human_approved)
- Gateway lyssnar localhost only (single-user)
- LLM-prompts loggas men secrets ar redacted i log-output

## 9. Vad som EJ ar bestamt har (refs OPEN_QUESTIONS.md)

- Postgres hosting i Fas 1 (lokal vs Neon vs Railway)
- Frontend-ramverk subval (App Router vs Pages Router)
- Demo-domaner for Fas 7
- Doppler-konto-setup (kan deferras till Fas 5)

## 10. Skeptic challenges (push-back applicerad)

Chief Skeptic (intern roll) utmanade arkitekturen pa minst foljande punkter:

| # | Skeptic-fraga | Planner-svar |
|---|---|---|
| S1 | "Globalt adapter-registry skapar central felpunkt — om en adapter ar buggig pavekas ALLA projekt" | Per-projekt versions-pinning (project_adapters-tabell) gor att projekt valjer nar de uppgraderar. En buggig v3 paverkar inte projekt som pinnat v2. |
| S2 | "E2B free tier har rate-limit som blir tight nar Engineer-loop genererar 10 adaptrar/timme" | Codespaces fallback (90h/man via Education Pack) for length runs; Local fallback med explicit --unsafe-local-flag for offline-utveckling. Cost-cap stoppar Engineer-loop innan rate-limit ramt. |
| S3 | "ToolRegistry i Fas 1 ar premature for en MVP" | Action parity ar arkitekturell, inte feature. Att lagga den retroaktivt kostar refactor av Fas 2–5. Att lagga den nu ar ~50 rader Pydantic. |
| S4 | "Replay-mode med adapter-version pinning kraver schema-migration varje gang adapter andras" | Lake records har adapter_version-kolumn redan fran Fas 1. Schema-migration sker inte for varje ny adapter — bara en gang. JSONB swallows resten. |
| S5 | "Single-user no-auth gor det omojligt att exponera maskinen senare utan totalrefactor" | Gateway ar tunn (FastAPI middleware-pattern). Auth-lager kan slangas pa som middleware utan att rora primitives. Multi-tenant kraver dock projekt_id-isolation pa db-niva — det finns redan (D5). |

Skeptic kvitterade efter dessa svar.
