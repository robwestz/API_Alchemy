# API Alchemy Engine

> **A self-extending data-product engine.** Give it a domain (`"fintechs in Sweden"`, `"expired domains with backlinks"`, `"SEO SERP data"`) and a swarm of agents over a shared workspace turns it into a useful data product — schema, REST API, insight report, product brief — while teaching itself new API integrations and ranking them on a leaderboard.

[![Phase status](https://img.shields.io/badge/phase-6a%20foundation-emerald)]() [![Tests](https://img.shields.io/badge/tests-42%2F42%20passing-emerald)]() [![Build](https://img.shields.io/badge/build-green-emerald)]()

## What this is — and what it isn't

**This is** a meta-machine. It produces dataset → schema → insights → OpenAPI spec → product brief end-to-end. Three self-loops make it *compounding*, not just functional:

| Loop | What it learns | Where it persists |
|---|---|---|
| **Self-discovering** | Which public APIs exist for a domain | `discovery_index` (Lake) |
| **Self-extending** | How to talk to a new API (Pydantic + adapter code) | `adapter_manifests` + `adapters/` |
| **Self-evaluating** | Which API is best at what (latency, density, cost, DX) | `arena_scores` (Lake) |

**This is not**:
- A clone of designarena.ai (the leaderboard is *one* output of the Arena layer)
- A SaaS product to sell — we *dogfood* it; products that fall out of it can be sold
- A LangChain wrapper with a chat next to a dashboard
- A no-code builder for non-technical users
- Tied to a specific LLM provider — LiteLLM abstraction is mandatory
- Hard-coded to any specific API — **zero** API-specific `if` statements in orchestrator/runtime

## Capability map

| # | Capability | One-line |
|---|---|---|
| C1 | **Ingest** | URL / API endpoint / pasted JSON-CSV / uploaded file → normalised events |
| C2 | **Universal Data Lake** | Postgres + JSONB. Swallows any API response without migration. Row-level lineage. |
| C3 | **Discovery (Scout)** | Domain/idea → relevant public APIs, ranked list |
| C4 | **Adapter Factory (Engineer)** | API doc → Pydantic model + adapter class + tests. Sandbox-validated before import. |
| C5 | **Schema Inference** | Raw records → suggested Postgres schema, relationships, warnings |
| C6 | **Insight Generation** | Profiled data → 5 patterns, 5 questions, 5 enrichments, 5 dashboards |
| C7 | **API Spec Generation** | Schema → OpenAPI spec + sample response + filter params |
| C8 | **Product Brief Generation** | Everything above → product name, target user, pain, MVP, pricing hypothesis |
| C9 | **Arena / Leaderboard (Judge)** | Latency, data density, cost/1k calls, DX score per API. Updated every run. |
| C10 | **Project Workspace** | All of the above scoped per project; agent and user share the exact same state tree |
| C11 | **Activity Log + Memory** | Every agent action logged, project context stored, completion state explicit |
| C12 | **Self-Repair** | Pydantic validation error → trigger Engineer to update the adapter |

## Architecture at a glance

```
+--------------------------------------------------------+
|  Frontend (Next.js + Tailwind + shadcn)                |  Phase 6
|  - Renders UI from tool_registry (action parity)       |
+----------------------+---------------------------------+
                       | WebSocket + REST
+----------------------v---------------------------------+
|  Gateway (FastAPI, localhost-only single-user)         |  Phase 1
+----------------------+---------------------------------+
                       |
+----------------------v---------------------------------+
|  Orchestrator + Atomic Primitives                      |  Phase 1
|  - Pure functions, Pydantic in/out                     |
|  - Each one is a tool_call (action-parity source)      |
+----------------------+---------------------------------+
        |                              |
+-------v-------+              +-------v-------+
| Adapters      |              | Agents        |   Phase 3-5
| (registry,    |              | Scout,        |
|  versioned)   |              | Engineer,     |
|               |              | Judge         |
+-------+-------+              +-------+-------+
        |                              |
        | (validated I/O via Pydantic) |
        v                              v
+--------------------------------------------------------+
|  Data Lake (Postgres + JSONB)                          |  Phase 1
|  projects, events, records, agent_actions, tool_calls, |
|  arena_scores, adapter_manifests, discovery_index,     |
|  cost_ledger, project_adapters                         |
+--------------------------------------------------------+
                       ^
+----------------------+---------------------------------+
|  LiteLLM (single source of LLM calls + cost-callback)  |  Phase 1
+----------------------+---------------------------------+
                       |
+----------------------v---------------------------------+
|  Sandbox (E2B default, Codespaces fallback)            |  Phase 3
|  - Auto-generated adapter code runs HERE first         |
|  - network=none default, opt-in per call               |
+--------------------------------------------------------+
```

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the full lager-stack with self-loops, action-parity mechanism, cost-cap design, and reproducibility/replay.

## Phase status

| Phase | Scope | Status |
|---|---|---|
| **0** — Architecture & Planning | 11 design docs + Pydantic interfaces | ✅ done |
| **1** — Skeleton + Lake + Tool Registry | Postgres schema (10 tables), FastAPI gateway, LiteLLM wrapper, ToolRegistry with health_check | ✅ done — 9/9 tests |
| **2** — Manual adapter (proof of plumbing) | open-meteo adapter, deterministic profiler + schema inference, `python -m alchemy ingest <url>` CLI | ✅ done — 7/7 tests + **CLI verified live** |
| **3a** — Adapter Factory skeleton | EngineerAgent (LLM → AdapterDraft → deterministic code-gen → sandbox), SandboxRunner (E2B + LocalProcess), SecretsResolver (LocalToml + Doppler) | ✅ done — 14/14 tests |
| **4** — Discovery Engine (Scout) | ScoutAgent with cost-cap, retry, optional web_search/fetch hooks → DiscoveryReport | ✅ done — 5/5 tests |
| **5** — Arena / Leaderboard | JudgeAgent benchmarks (p50/p95 latency, fields, cost, DX), `compute_ranking()` with configurable weights | ✅ done — 6/6 tests |
| **6a** — Lab UI foundation | Next.js 15 + Tailwind v4 + shadcn-stack, 3-column layout, Source tab, ToolButton (codegen from ToolSpec) | ✅ done — build green |
| **6b** — Remaining tabs | Dataset, Schema, Insights, API Spec, Brief, Agent Log, Arena | 🔜 next |
| **6c** — Realtime + e2e | WebSocket subscription, Playwright e2e, action-parity CI test | 🔜 |
| **7** — Dogfood + Showcase | 3 demo domains end-to-end + critical SHOWCASE_AUDIT.md | 🔜 (requires LLM key) |

**Test totals (all green)**: 42 runnable tests pass; 6 skipped pending operator setup (`TEST_DATABASE_URL` for smoke tests + real-API-gate for open-meteo).

## Quickstart — what works *right now without API keys*

```bash
# 0. Clone
git clone https://github.com/robwestz/API_Alchemy.git
cd API_Alchemy

# 1. Backend — Python 3.11+
pip install -e ".[dev]" --no-build-isolation
PYTHONPATH=. python -m pytest tests/test_action_parity.py -v   # 9/9 pass, no DB needed

# 2. CLI live against open-meteo (real public API, no key needed)
PYTHONPATH=. python -m packages.cli ingest \
  "https://api.open-meteo.com/v1/forecast?latitude=59.33&longitude=18.07&current=temperature_2m,relative_humidity_2m,wind_speed_10m"
# → fetches real records → profiles 17 fields → generates Postgres schema

# 3. Frontend — Node 20+
cd packages/frontend
npm install --legacy-peer-deps
npm run dev   # http://localhost:3000
```

The frontend has graceful degradation — it shows offline states cleanly when the backend is not running.

## Endpoints (when gateway is up)

| Method | Path | Description |
|---|---|---|
| GET | `/health` | System status |
| GET | `/api/tools` | List registered primitives (Tool Registry) — *frontend codegens UI from this* |
| POST | `/api/tools/{name}` | Execute a primitive |
| GET / POST | `/api/projects` | List / create projects |
| GET | `/api/projects/{id}` | Get specific project |
| WS | `/ws/projects/{id}` | Per-project event stream |

Interactive API docs at `http://127.0.0.1:8000/docs` (FastAPI auto-generated).

## Architectural principles (non-negotiable)

| Principle | What it means concretely |
|---|---|
| **Action parity** | Anything the user can do in the UI, an agent can do via tools. Same endpoint, same state tree. No "agent-only" or "UI-only" features. |
| **Atomic primitives** | No `analyze_data()` mega-tool. Workflow = composition of `ingest`, `parse`, `profile`, `infer_schema`, `generate_insights`, `generate_api_spec`, `generate_brief`. New workflow = new composition, not new tool. |
| **LiteLLM abstraction** | All LLM traffic through `litellm.completion(...)`. Model name is config, never hardcoded. |
| **Pydantic strict flow** | Every API response validated through Pydantic. Schema drift = exception → Self-Repair trigger. |
| **Instructor for structured output** | Agents return JSON that follows Pydantic schema. No regex parsing of LLM text. |
| **Same-state principle** | Agent and user read/write the same `project_state` (Postgres + WebSocket broadcast). No separate "agent memory" that diverges. |
| **Sandbox for all auto-generated code** | Adapter Factory output never runs in main process first. E2B isolation + network policy + manifest-declared secrets only. |
| **Reproducibility** | Every generated adapter saved with: prompt, model, version, docs read. Every adapter version pinned per project; replay-cursor reproduces exact historical runs. |

## Documentation

| File | Contents |
|---|---|
| [PROJECT_BRIEF.md](PROJECT_BRIEF.md) | North star, capability map, anti-goals |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Lager-stack, three self-loops, action parity, cost control |
| [DECISIONS.md](DECISIONS.md) | D1–D8: locked architectural decisions with rationale |
| [PHASE_PLAN.md](PHASE_PLAN.md) | Phase 0–7 with DoD per phase (YAML compound markers parseable by harness) |
| [RISK_REGISTER.md](RISK_REGISTER.md) | R1–R18 with severity, mitigation, status |
| [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) | Blocking questions for next phase + nice-to-have backlog |
| [AGENT_ROLES.md](AGENT_ROLES.md) | Build-time vs runtime agents, identity model, dispatch model |
| [DOD_MATRIX.md](DOD_MATRIX.md) | Per-phase DoD checks with cost/time estimates |
| [GAP_SCAN.md](GAP_SCAN.md) | Phase 0 GAP SCAN with intent reground |
| [ENV_SETUP.md](ENV_SETUP.md) | Postgres setup (Neon default / local) |
| [docs/phase-3-design/](docs/phase-3-design/) | Engineer-agent + sandbox + flow design specs |

## Testing

```bash
# All Python tests (no DB required for action-parity, agent-tests, sandbox-tests)
PYTHONPATH=. pytest tests/ -v

# Integration tests with Postgres
TEST_DATABASE_URL=postgres://user:pass@host/testdb pytest tests/integration/ -v -m integration

# Real-API gate for open-meteo (verifies mock matches reality)
OPEN_METEO_REAL_API=1 pytest tests/integration/test_open_meteo_e2e.py::test_fetch_with_real_api

# Frontend
cd packages/frontend
npm run build      # Type-checks + bundles
npm run dev        # Dev server on :3000
```

## How this was built (compound-agent harness)

This codebase was developed using a build-time agent harness:

- **claude-opus-4.7** as Lead Architect (planning, design review, verification)
- **claude-sonnet-4.6** as Senior Implementer (per-phase code dispatch)
- **Compound Protocol** ledger (`.agents/TASKS.json` in parent repo, gitignored here) tracks every phase as a task with verifiable Definition of Done

Each phase: open ledger task → dispatch Sonnet sub-agent with full context (interfaces, decisions, design docs) → Opus reviews output → DoD verify → COMPOUND REGISTER block logged → next phase.

## License

Proprietary — single-operator dev. License decision deferred to Phase 7 (post-dogfood).

## Acknowledgements

Built with [LiteLLM](https://github.com/BerriAI/litellm), [Pydantic](https://pydantic.dev/), [Instructor](https://python.useinstructor.com/), [FastAPI](https://fastapi.tiangolo.com/), [Next.js](https://nextjs.org/), [shadcn/ui](https://ui.shadcn.com/), [Loguru](https://github.com/Delgan/loguru), and [E2B](https://e2b.dev/) sandboxes.
