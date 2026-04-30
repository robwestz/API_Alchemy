---
compound: active
phases:
  - id: phase-1-skeleton
    goal: "Skeleton + Universal Data Lake + Tool Registry"
    dod:
      - check: test
        command: "pytest tests/integration/test_smoke.py"
      - check: artifact
        path: "docker-compose.yml"
      - check: artifact
        path: "packages/orchestrator/primitives/_registry.py"
      - check: manual
        description: "docker compose up bringar alla services healthy"
    skills: ["cursor-llm-dev"]
  - id: phase-2-manual-adapter
    goal: "Manual adapter path (proof of plumbing) — open-meteo end-to-end"
    dod:
      - check: test
        command: "pytest tests/integration/test_open_meteo_e2e.py"
      - check: artifact
        path: "packages/adapters/open_meteo/__init__.py"
      - check: manual
        description: "URL till open-meteo paste:ad i CLI ger Postgres-schema ut"
    skills: ["cursor-llm-dev"]
  - id: phase-3-adapter-factory
    goal: "Adapter Factory (Engineer-agent) med E2B sandbox"
    dod:
      - check: test
        command: "pytest tests/integration/test_engineer_agent.py"
      - check: manual
        description: "3 publika API:er testade; 2/3 ger fungerande adapter pa forsta forsoket"
      - check: manual
        description: "Adapter-kod kan inte gora natverksanrop utanfor adaptern"
    skills: ["cursor-llm-dev", "playwright"]
  - id: phase-4-discovery
    goal: "Discovery Engine (Scout-agent)"
    dod:
      - check: test
        command: "pytest tests/integration/test_scout_agent.py"
      - check: manual
        description: "fintech i Sverige ger >=5 relevanta kandidater varav >=2 anvandbara"
    skills: ["cursor-llm-dev"]
  - id: phase-5-arena
    goal: "Arena / Leaderboard (Judge-agent)"
    dod:
      - check: test
        command: "pytest tests/benchmarks/test_judge.py"
      - check: manual
        description: "Minst 3 adaptrar bench:ade; leaderboard uppdateras live via WebSocket"
    skills: ["cursor-llm-dev"]
  - id: phase-6-lab-ui
    goal: "Lab UI (Next.js + tabs som tacker hela actionytan)"
    dod:
      - check: test
        command: "pnpm playwright test tests/e2e/lab_full_flow.spec.ts"
      - check: manual
        description: "Action parity verifierad via tests/test_action_parity.py"
    skills: ["cursor-llm-dev", "vercel-deploy"]
  - id: phase-7-dogfood
    goal: "Dogfood + Showcase audit (3 demo-domaner)"
    dod:
      - check: artifact
        path: "docs/SHOWCASE_AUDIT.md"
      - check: manual
        description: "3 kompletta produktbriefer producerade utan manuell intervention"
    skills: ["showcase-presenter"]
---

# PHASE_PLAN — API Alchemy Engine

> Forfinad version av startpaketets fas-plan. Datum: 2026-04-30. Planner: claude-opus-4.7.
> Compound markers ovan ar maskinlasbara — kor `node ../.agents/task.mjs import api-alchemy-engine/PHASE_PLAN.md` for att forhandsvisa import till ledger.

---

## Fas 0 — Gap Scan & Architecture Forge (PAGAR via t-006)

| | |
|---|---|
| Lead | Lead Architect (claude-opus-4.7) |
| Subagents | Chief Skeptic (intern roll) |
| Skills | architecture-audit, 200k-blueprint |
| Context budget | ~40k input + ~20k output |
| Inputs | startpaket, compound-agent-system upgrade-spec |
| Outputs | 10 artefakter per ledger-task t-006 DoD |
| DoD | (a) Skeptic-pushback (ARCHITECTURE.md sektion 10). (b) interfaces/__init__.py mypy strict. (c) OPEN_QUESTIONS.md har <=5 blockerande fragor. (d) Operator-signoff. |

## Fas 1 — Skeleton + Universal Data Lake + Tool Registry

| | |
|---|---|
| Lead | Senior Implementer (Sonnet sub-agent) |
| Subagents | Verifier (Sonnet sub-agent) |
| Skills | cursor-llm-dev |
| Context budget | ~60k |
| Inputs | Fas 0 outputs |
| Outputs | docker-compose.yml, Postgres-schema, LiteLLM-konfig, Pydantic baseclasses, Loguru config, health-endpoints, ToolRegistry med >=1 registrerad primitive |
| DoD | docker compose up -> services healthy. pytest smoke gront. WebSocket-broadcast nar frontend-stub. Tool registry-test pass. |
| Avvikelse | Tool Registry inforas i Fas 1 (D6) — UI-konsumtion fortfarande Fas 6. |

## Fas 2 — Manual Adapter Path (proof of plumbing)

| | |
|---|---|
| Lead | Senior Implementer |
| Subagents | Verifier, Showcase Auditor |
| Outputs | open-meteo adapter, parser, schema-inference, ingest -> lake -> schema-output, CLI `python -m alchemy ingest <url>` |
| DoD | URL -> JSON i Lake -> Postgres-schema ut. Inga LLM-anrop. |
| Risk gates | Special-casing av open-meteo i pipen -> arkitekturen ar fel. |

## Fas 3 — Adapter Factory (Engineer-agent)

| | |
|---|---|
| Lead | Lead Architect (design) -> Senior Implementer (bygge) |
| Subagents | Verifier, Chief Skeptic (sakerhetsgranskning) |
| Skills | cursor-llm-dev, playwright |
| Outputs | Engineer-agent: doc-URL -> Pydantic + adapter + test -> E2B sandbox -> human_approved -> register. Manifest i Lake. |
| DoD | (a) 3 API:er testade, 2/3 fungerar forsta forsoket. (b) Sandbox network=none verifierat. (c) Re-generation byte-identisk. (d) human_approved-flow funkar. |
| Risk gates | Sandbox ej implementerad och testad -> STOPP. |

## Fas 4 — Discovery Engine (Scout-agent)

| | |
|---|---|
| Lead | Senior Implementer |
| Subagents | Verifier |
| Outputs | Scout: doman -> DiscoveryReport (Pydantic) med rankad kandidatlista. Auto-koppling till Engineer for top-N. |
| DoD | "fintech i Sverige" -> >=5 kandidater, >=2 anvandbara. Cost-cap respekteras. |
| Risk gates | Hallucinerade API:er = fail. Engineer maste verifiera doc-URL. |

## Fas 5 — Arena / Leaderboard (Judge-agent)

| | |
|---|---|
| Lead | Senior Implementer |
| Subagents | Verifier |
| Outputs | Judge benchmark: latens (p50/p95), tathet, kostnad/1000, DX-score. Sparas i arena_scores. Frontend-tab leaderboard live. |
| DoD | >=3 adaptrar bench:ade. Live WebSocket-uppdatering. Vikter konfigurerbara per projekt. |

## Fas 6 — Lab UI

| | |
|---|---|
| Lead | Senior Implementer |
| Subagents | Verifier, Showcase Auditor |
| Skills | cursor-llm-dev, vercel-deploy |
| Outputs | Next.js + Tailwind + shadcn UI: tabs Source/Dataset/Schema/Insights/API Spec/Product Brief/Agent Log/Arena. Action parity. WebSocket realtid. |
| DoD | (a) Demo-dataset -> schema/insights/brief utan terminal. (b) Agent-lage kor hela kedjan, Activity Log syns. (c) playwright-test gront. |
| Risk gates | UI utan motsvarande tool_call -> action parity bruten -> STOPP. |

## Fas 7 — Dogfood & Showcase (kritisk sjalvkritik)

| | |
|---|---|
| Lead | Showcase Auditor (claude-opus-4.7) |
| Subagents | Chief Skeptic |
| Skills | showcase-presenter |
| Outputs | 3 dogfood-korningar mot 3 demo-domaner. SHOWCASE_AUDIT.md med arlig kritik. |
| DoD | (a) 3 kompletta produktbriefer utan manuell intervention. (b) Audit ar kritisk, inte saljande. |

---

## Fas-overgangar och Compound Register

Efter varje fas: COMPOUND-block i .agents/COMPOUND_LOG.md per `.agents/COMPOUND.md`. Vid fas-overgang: CONTEXT REFRESH per mekanism 3.

## Subagent-dispatch-modell

Build-time:
- claude-opus-4.7 (planner+verifier denna session) dispatchar via Claude Code Task-tool med model=sonnet for executor-arbete
- Codex-agenter kan kallas via .codex/-config — separat process via Bash, koordinering via .agents/TASKS.json
- Verifier kor DoD-checks via `node ../.agents/task.mjs verify <id>` efter varje fas

Runtime (inne i produkten):
- Scout, Engineer, Judge, Profiler, Insight Generator, Productizer, Orchestrator-agent
- Modellval per agent ar config i packages/agents/<name>/config.toml — inte hardkodat
