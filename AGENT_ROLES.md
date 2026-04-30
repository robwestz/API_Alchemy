# AGENT_ROLES — API Alchemy Engine

> Datum: 2026-04-30. Foljer compound-agent-system upgrade-spec P4 (normaliserad identity).
> Tva tier: build-time (de som bygger maskinen) och runtime (de som lever inne i den fardiga maskinen).

---

## 1. Build-time roller (utanfor produkten)

Dessa ar harness + subagenter. De bygger API Alchemy Engine.

| Role | Client | Model | Ledger ID pattern | Responsibility |
|---|---|---|---|---|
| Lead Architect | claude-code | opus-4.7 | opus-architect | Designar, granskar, signerar arkitektur. Driver Fas 0 och alla fas-overgangar. |
| Chief Skeptic | claude-code | opus-4.7 | opus-skeptic | Utmanar antaganden. Push-back vid Fas 0 + varje fas-end. Skriver risk-uppdateringar. |
| Senior Implementer | claude-code | sonnet-4.6 | sonnet-impl-{n} | Skriver kod enligt plan. Spawnas per Fas via Task-tool. |
| Verifier | claude-code | sonnet-4.6 | sonnet-verify-{n} | Kor DoD-checks. Spawnas per Fas. Approves inte utan gron kedja. |
| Showcase Auditor | claude-code | opus-4.7 | opus-showcase | Arlig utvardering vid milstolpar. Skriver SHOWCASE_AUDIT.md i Fas 7. |
| Codex Implementer (alt) | codex-cli | gpt-5-codex | codex-impl-{n} | Alternativ executor for parallella chunks som inte krockar med Sonnet. |
| Operator | (human) | (n/a) | human-robin | Final authority. DoD-signoff. Direction. |

### Dispatch-modell

- I denna session ar jag Lead Architect + Chief Skeptic + Verifier (planner+verifier-roll i ledgern, signed in som claude-opus-4.7 — legacy ID per D8).
- Senior Implementer-arbete spawnas via Claude Code Task-tool med `model: "sonnet"` och `subagent_type: "general-purpose"` (eller specifik specialist agent for review/verification).
- Codex-agenter kallas via Bash mot `.codex/`-config nar lampligt (parallella chunks, ej sandbox-kritiska).
- Verifier kor `node ../.agents/task.mjs verify <id>` efter varje fas.

### Modellval per fas (default)

| Fas | Lead | Subagents | Skal |
|---|---|---|---|
| Fas 0 | opus-architect | opus-skeptic | Arkitektur kraver djup. Skeptic-pushback kraver opus. |
| Fas 1 | sonnet-impl-1 | sonnet-verify-1 | Skeleton, mekaniskt arbete. |
| Fas 2 | sonnet-impl-1 | sonnet-verify-1 | Manuell adapter, mekaniskt. |
| Fas 3 | opus-architect (design) -> sonnet-impl-2 (bygge) | opus-skeptic, sonnet-verify-2 | Engineer-agent design ar arkitektur-paverkande. |
| Fas 4 | sonnet-impl-3 | sonnet-verify-3 | Scout — primarily prompt engineering + LiteLLM. |
| Fas 5 | sonnet-impl-3 | sonnet-verify-3 | Judge — benchmarking. |
| Fas 6 | sonnet-impl-4 | sonnet-verify-4, opus-showcase | Frontend, action parity. |
| Fas 7 | opus-showcase | opus-skeptic | Showcase audit kraver opus arlighet. |

---

## 2. Runtime agents (inne i den fardiga maskinen)

Dessa ar agenter som operatoren / produktanvandaren kommer kalla pa. De definieras i `packages/agents/<name>/` och foljer `BaseAgent`-kontraktet.

| Agent | Role i produkten | Tool-allowlist (default) | Modell-default |
|---|---|---|---|
| Scout | Discovery — doman -> API-kandidater | web_search, web_fetch, read_docs, evaluate_api | sonnet-4.6 |
| Engineer | Adapter Factory — doc-URL -> Pydantic + adapter + test | read_doc, write_pydantic_model, write_adapter, sandbox_test, register_adapter | opus-4.7 |
| Judge | Arena — bench:a registrerade adaptrar | run_benchmark, score_api, update_leaderboard | sonnet-4.6 |
| Profiler | Dataset-tab — analysera fields | profile_field, detect_type, compute_null_rate | sonnet-4.6 |
| Insight Generator | Insights-tab | find_patterns, suggest_questions, suggest_enrichments | sonnet-4.6 |
| Productizer | Brief-tab | define_target_user, define_mvp, propose_pricing | opus-4.7 |
| Orchestrator-agent | Cross-cutting komposition | (alla atomic primitives, men maste deklarera vilka per anrop) | opus-4.7 |

Modellval ar config i `packages/agents/<name>/config.toml` — INTE hardkodat. LiteLLM-abstraktion gor att operator kan svinga till annan leverantor.

### Tool-allowlist enforcement

`BaseAgent.tool_allowlist: list[str]` definierar vilka primitives agenten far kalla. `ToolRegistry`-handler verifierar mot allowlist innan exekvering. Brott loggas i `agent_actions` med `denied_reason`.

---

## 3. Identity-modell (per upgrade-spec P4)

| Falt | Beskrivning | Exempel |
|---|---|---|
| client | Vilken CLI / SDK | claude-code, codex-cli, cursor |
| model | Underliggande LLM | opus-4.7, sonnet-4.6, gpt-5-codex |
| role | Vad rollen gor | planner, executor, reviewer, verifier, operator |
| ledger_agent_id | Stabil id i .agents/TASKS.json | opus-architect, sonnet-impl-3 |
| session_id | UUID per session | (genereras automatiskt) |
| display_name | Human-readable label | "Opus Architect", "Sonnet Implementer #3" |

Sessionen 2026-04-30:
- client = claude-code
- model = opus-4.7
- role = planner+verifier
- ledger_agent_id = claude-opus-4.7 (legacy; bor migreras till opus-architect i framtida ack-flow)
- display_name = "Opus Architect"

---

## 4. Anti-patterns

- Blanda build-time och runtime ledger: build-time tasks loggas i parent `api_wrapper/.agents/TASKS.json`. Runtime agent_actions loggas i Lake. ALDRIG i samma tabell.
- Hardkoda modellnamn i agent-kod: forbjudet. Modellnamn ar config.
- Spawn:a sub-agent utan ledger-task: PROTOCOL.md regel 1 — no work without a task.
- Verifier som approves utan att ha kort DoD-check: protokollbrott. DoD-status ar maskinverifierad.

---

## 5. Skill-attribution per agent

Build-time agenter foljer harness-skill-system (`.agents/skills/` + `.claude/skills/`). Runtime agenter foljer `packages/agents/<name>/skill_pack/` (separat fran harness).

Skill-listan for build-time finns i `.agents/SKILL_SELECT.md`. Skill-listan for runtime byggs ut allteftersom — borjar tom i Fas 1.
