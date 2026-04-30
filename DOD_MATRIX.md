# DOD_MATRIX — API Alchemy Engine

> Sammanstallning av alla DoD-checks per fas. Datum: 2026-04-30.
> Kompletterar PHASE_PLAN.md med kostnad/tid och vem-signerar.
> Foljer .agents/DOD.md tre check-typer: test, artifact, manual.

---

## Fas 0 — t-006 (PAGAR)

| Check-typ | Kommando / Path / Beskrivning | Vem signerar | Kostnad |
|---|---|---|---|
| artifact | api-alchemy-engine/PROJECT_BRIEF.md | filesystem | 0 |
| artifact | api-alchemy-engine/GAP_SCAN.md | filesystem | 0 |
| artifact | api-alchemy-engine/DECISIONS.md | filesystem | 0 |
| artifact | api-alchemy-engine/ARCHITECTURE.md | filesystem | 0 |
| artifact | api-alchemy-engine/PHASE_PLAN.md | filesystem | 0 |
| artifact | api-alchemy-engine/RISK_REGISTER.md | filesystem | 0 |
| artifact | api-alchemy-engine/OPEN_QUESTIONS.md | filesystem | 0 |
| artifact | api-alchemy-engine/AGENT_ROLES.md | filesystem | 0 |
| artifact | api-alchemy-engine/DOD_MATRIX.md | filesystem | 0 |
| artifact | api-alchemy-engine/packages/interfaces/__init__.py | filesystem | 0 |
| manual | Skeptic-pushback minst en gang med svar | Lead Architect (dokumenterat i ARCHITECTURE.md sektion 10) | 0 |
| manual | Operator bekraftar Fas 0 artefakter innan Fas 1 oppnas | human-robin | 0 |

---

## Fas 1 — Skeleton + Lake + Tool Registry

| Check-typ | Kommando / Path / Beskrivning | Vem signerar | Kostnad |
|---|---|---|---|
| test | pytest tests/integration/test_smoke.py | sonnet-verify-1 | $0.5–2 LLM, 30s |
| test | pytest tests/test_action_parity.py | sonnet-verify-1 | <30s |
| artifact | docker-compose.yml (eller pg_ctl-skript om Docker undviks) | filesystem | 0 |
| artifact | packages/orchestrator/primitives/_registry.py | filesystem | 0 |
| artifact | packages/lake/migrations/001_initial.sql | filesystem | 0 |
| artifact | packages/llm/litellm_wrapper.py | filesystem | 0 |
| manual | Alla services healthy | sonnet-verify-1 | 0 |
| manual | WebSocket-broadcast nar frontend-stub | sonnet-verify-1 | 0 |
| manual | Operator-signoff Fas 1 | human-robin | 0 |

---

## Fas 2 — Manual Adapter Path (open-meteo)

| Check-typ | Kommando / Path / Beskrivning | Vem signerar | Kostnad |
|---|---|---|---|
| test | pytest tests/integration/test_open_meteo_e2e.py | sonnet-verify-1 | <30s |
| artifact | packages/adapters/open_meteo/__init__.py | filesystem | 0 |
| artifact | packages/adapters/open_meteo/manifest.json | filesystem | 0 |
| artifact | packages/parser/profile.py | filesystem | 0 |
| artifact | packages/lake/schema_inference.py | filesystem | 0 |
| manual | URL till open-meteo paste:ad i CLI ger Postgres-schema ut | sonnet-verify-1 | 0 |
| manual | Operator-signoff Fas 2 | human-robin | 0 |

---

## Fas 3 — Adapter Factory (Engineer-agent)

| Check-typ | Kommando / Path / Beskrivning | Vem signerar | Kostnad |
|---|---|---|---|
| test | pytest tests/integration/test_engineer_agent.py | sonnet-verify-2 | $1–3 LLM (mockad) |
| test | pytest tests/security/test_sandbox_isolation.py | opus-skeptic | 0 (mock-test) |
| artifact | packages/agents/engineer/__init__.py | filesystem | 0 |
| artifact | packages/sandbox/e2b_runner.py | filesystem | 0 |
| manual | 3 publika API:er testade; 2/3 fungerar forsta forsoket | opus-architect + human-robin | $5–15 LLM |
| manual | Adapter-kod kan inte gora natverksanrop utanfor adaptern | opus-skeptic | 0 |
| manual | Re-generation fran manifest ger byte-identisk eller semantiskt ekvivalent kod | sonnet-verify-2 | $2–5 LLM |
| manual | UI-prompt for human_approved fungerar | human-robin | 0 |
| manual | Operator-signoff Fas 3 | human-robin | 0 |

---

## Fas 4 — Discovery Engine (Scout-agent)

| Check-typ | Kommando / Path / Beskrivning | Vem signerar | Kostnad |
|---|---|---|---|
| test | pytest tests/integration/test_scout_agent.py | sonnet-verify-3 | $1–3 LLM |
| artifact | packages/agents/scout/__init__.py | filesystem | 0 |
| artifact | packages/agents/scout/discovery_report.py | filesystem | 0 |
| manual | "fintech i Sverige" -> >=5 kandidater varav >=2 anvandbara | sonnet-verify-3 + human-robin | $2–5 LLM + web_search |
| manual | Cost-cap respekteras | sonnet-verify-3 | 0 |
| manual | Inga hallucinerade API:er | sonnet-verify-3 | 0 |
| manual | Operator-signoff Fas 4 | human-robin | 0 |

---

## Fas 5 — Arena (Judge-agent)

| Check-typ | Kommando / Path / Beskrivning | Vem signerar | Kostnad |
|---|---|---|---|
| test | pytest tests/benchmarks/test_judge.py | sonnet-verify-3 | <2 min |
| artifact | packages/agents/judge/__init__.py | filesystem | 0 |
| artifact | packages/lake/migrations/00X_arena_scores.sql | filesystem | 0 |
| manual | Minst 3 adaptrar bench:ade | sonnet-verify-3 | $0–2 |
| manual | Leaderboarden uppdateras live (WebSocket) | sonnet-verify-3 | 0 |
| manual | Vikter konfigurerbara per projekt | sonnet-verify-3 | 0 |
| manual | Operator-signoff Fas 5 | human-robin | 0 |

---

## Fas 6 — Lab UI

| Check-typ | Kommando / Path / Beskrivning | Vem signerar | Kostnad |
|---|---|---|---|
| test | pnpm playwright test tests/e2e/lab_full_flow.spec.ts | sonnet-verify-4 | <5 min |
| test | pytest tests/test_action_parity.py (refresh) | sonnet-verify-4 | <30s |
| artifact | packages/frontend/app/page.tsx | filesystem | 0 |
| artifact | packages/frontend/components/ToolButton.tsx | filesystem | 0 |
| manual | Anvandare kan ladda demo-dataset -> schema/insights/brief utan terminal | opus-showcase + human-robin | $2–10 LLM |
| manual | Agent-lage kor hela kedjan; Activity Log syns | opus-showcase | $5–15 LLM |
| manual | Operator-signoff Fas 6 | human-robin | 0 |

---

## Fas 7 — Dogfood & Showcase

| Check-typ | Kommando / Path / Beskrivning | Vem signerar | Kostnad |
|---|---|---|---|
| artifact | docs/SHOWCASE_AUDIT.md | filesystem | 0 |
| artifact | docs/dogfood/run-1-{domain}.md | filesystem | 0 |
| artifact | docs/dogfood/run-2-{domain}.md | filesystem | 0 |
| artifact | docs/dogfood/run-3-{domain}.md | filesystem | 0 |
| manual | 3 kompletta produktbriefer utan manuell intervention | opus-showcase + human-robin | $20–80 LLM |
| manual | Audit-dokumentet ar kritisk; Skeptic gor andra omgang om allt verkar perfekt | opus-skeptic | $5–10 LLM |
| manual | Operator-signoff Fas 7 (= maskinen anses klar) | human-robin | 0 |

---

## Total budget-uppskattning

| Fas | LLM-kostnad | Clock-tid | Compute-tid |
|---|---|---|---|
| Fas 0 | $0 | 1–3h | <30 min |
| Fas 1 | $1–3 | 4–8h | 1h |
| Fas 2 | $0 | 2–4h | <30 min |
| Fas 3 | $20–40 | 8–16h | 2h |
| Fas 4 | $5–15 | 4–8h | 1h |
| Fas 5 | $1–5 | 4–8h | 1h |
| Fas 6 | $20–40 | 12–24h | 2h |
| Fas 7 | $30–100 | 8–16h | 4h |
| Total | $80–200 | 43–87h | 12h |

Grova uppskattningar. cost_ledger i produktion ger exakta siffror.

---

## DoD-anti-patterns (per .agents/DOD.md)

- DoD for latt (`test:echo ok`) — flagged av COMPOUND REGISTER specificitet
- DoD andrad mid-task — kraver `--reason` flag, loggas
- `check: manual` rubber-stamped av operator — operatoren ansvarar
- `check: test` flaky — ny task: "Stabilize flaky test X"
