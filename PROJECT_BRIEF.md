# PROJECT_BRIEF — API Alchemy Engine

> Källa: `startpaket_projektidé_api_alchemy_engine.md` (parent workspace).
> Detta dokument är en kondenserad version som lagras med projektet.

## North Star

En autonom motor som tar en idé eller domän-uttryck (`"svenska fintechs"`, `"expired domains med backlinks"`, `"SEO SERP-data"`) och producerar — via en svärm av agenter över ett delat workspace — en användbar dataprodukt (normaliserat schema, REST-API, insight-rapport, product brief), samtidigt som den **bygger på sig själv** genom att lära sig nya API-integrationer och ranka dem i en leaderboard.

## Tre self-loops (det compounding-momentet)

| Loop | Lär sig | Lagras i |
|---|---|---|
| Self-discovering | Vilka publika API:er finns för en domän | `discovery_index` (Lake) |
| Self-extending | Hur man pratar med ett nytt API (Pydantic + adapter) | `adapter_manifests` + `adapters/` |
| Self-evaluating | Vilket API är bäst på vad (latens/täthet/pris/DX) | `arena_scores` (Lake) |

Saknas en av dessa → vanlig app, inte meta-maskin.

## Anti-Goals

- Inte en klon av designarena.ai
- Inte en SaaS-produkt vi säljer (vi dogfood:ar den)
- Inte en LangChain-wrapper med chatt bredvid dashboard
- Inte en generisk no-code-byggare
- Inte beroende av specifik LLM-leverantör (LiteLLM-abstraktion obligatorisk)
- Inte hårdkodad mot något specifikt API — noll API-specifika `if`-satser i orchestrator/runtime

## Kärnkapaciteter (capability map)

| # | Kapacitet | I kort |
|---|---|---|
| C1 | **Ingest** | URL / API-endpoint / JSON-CSV / upload → normaliserade events |
| C2 | **Universal Data Lake** | Postgres + JSONB. Sväljer godtycklig API-respons utan migrering. Lineage på rad-nivå. |
| C3 | **Discovery (Scout)** | Domän / idé → relevanta publika API:er, rankad lista |
| C4 | **Adapter Factory (Engineer)** | API-doc → Pydantic-modell + adapter + tester. Sandbox-validering. |
| C5 | **Schema Inference** | Råa records → Postgres-schema + relationer + varningar |
| C6 | **Insight Generation** | Profilerad data → 5 mönster, 5 frågor, 5 enrichments, 5 dashboards |
| C7 | **API Spec Generation** | Schema → OpenAPI-spec + sample response + filter-params |
| C8 | **Product Brief Generation** | Allt ovan → product name, target user, pain, MVP, prishypotes |
| C9 | **Arena / Leaderboard (Judge)** | Latens, datatäthet, kostnad/1000, DX-score per API |
| C10 | **Project Workspace** | Allt ovan paketerat per projekt; agent + user delar exakt samma state-träd |
| C11 | **Activity Log + Memory** | Varje agent-action loggas, projektkontext lagras, completion state explicit |
| C12 | **Self-Repair** | Pydantic-fel → trigga Engineer-agenten att uppdatera adaptern |

C1–C8 = table stakes. **C3, C4, C9, C12 = det som gör det till meta-maskin.**

## Repo och operational facts

- **Repo location**: `C:\Users\robin\Videos\api_wrapper\api-alchemy-engine\` (eget git-repo, separat från harness)
- **Harness**: `.agents/` ledger ligger i parent `api_wrapper/`, exkluderad via `.gitignore`
- **Operatör**: human-robin (single-user)
- **Build-time orchestration**: claude-opus-4.7 som planner/verifier, sonnet-subagenter som executors, ev. codex-agenter som executor-alt
- **Status**: Fas 0 (intake + arkitektur) — ledger-task `t-006`

## Slutord

Detta är inte ett projekt. Det är en investering i att alla framtida idéer ska kosta 10x mindre. Frestelsen är att hoppa till Fas 6 (Lab UI). Motstå. UI:t är *konsekvensen* av att C1–C12 funkar, inte tvärtom.
