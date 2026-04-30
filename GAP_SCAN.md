# GAP_SCAN — Fas 0

> Producerad 2026-04-30 av claude-opus-4.7 (planner-roll) infor Fas 0 av API Alchemy Engine.
> Format foljer `.agents/COMPOUND.md` mekanism 2 (GAP SCAN).

---

## INTENT REGROUND

Originalord fran operator (citat):

> "Bygg en autonom motor som tar en ide eller ett doman-uttryck och producerar — via en svarm av agenter over ett delat workspace — en anvandbar dataprodukt, samtidigt som den bygger pa sig sjalv genom att lara sig nya API-integrationer och ranka dem i en leaderboard."

Fardig version (vad det betyder konkret): operator sager "fintechs i Sverige" -> maskinen hittar API-kandidater (Scout) -> skriver sakra adaptrar (Engineer + sandbox) -> kor benchmark (Judge) -> producerar dataset + schema + insights + OpenAPI + brief -> allt reproducerbart, kostnadskontrollerat, med UI och agent-lage i paritet.

Plan covers (i startpaket): 12 capabilities, 9 arkitekturprinciper, 8 faser med DoD, build-time vs runtime-rolldelning, Risk Register R1–R10, mappstruktur.

Plan misses (kritiskt — tacks av DECISIONS.md):

- Var maskinen ska byggas (D1)
- Hur secrets for paid API:er hanteras (D3)
- Adapter-registry scope: per-projekt eller global (D2)
- Schema-evolution policy (D7)
- Sandbox-OS-strategi (D4)
- Single-user vs multi-tenant (D5)
- Frontend-stub i Fas 1 ar luddig — behover vara konkret for action-parity-test (tacks av PHASE_PLAN.md Fas 1)

## SHELL CHECK

Fas 0:s output ar avsiktligt en skiss (`interfaces/__init__.py`, dokument). Risken ar att vi designar `BaseAdapter` utan att ha gjort tankesteget mot en konkret API-respons -> laser in fel abstraktion.

Mitigering: vi designar interfacet med open-meteo (Fas 2:s manuella adapter) som "imagined first concrete instance". Annars hittar Fas 2 missar i interface-design nar det ar dyrt att andra.

## VISION COMPLETION (icke-uttryckt men troligen onskat)

| # | Hypotes | Klassning | Beslut |
|---|---|---|---|
| V1 | Replay-mode for historiska agent-korningar (givet "reproducibility" + lineage) | Important | Inkluderas i `interfaces/__init__.py` som `ReplayCursor`-koncept |
| V2 | Human-in-the-loop pa adapter-godkannande aven nar sandbox ar gron | Important | Inbakat i D4 sandbox-flode (generated -> sandbox_passed -> human_approved -> active) |
| V3 | Cross-project adapter-ateranvandning (compounding-loftet pa riktigt) | Critical | Beslut D2 (globalt registry) |
| V4 | Time-travel queries (data som den sag ut 2026-04-12) | Nice-to-have | Loggas i `OPEN_QUESTIONS.md` Q-NICE-1, byggs ej oprompt |
| V5 | Notebook-export av insights (insights -> Jupyter med samma queries) | Nice-to-have | Defer (Q-NICE-2) |

## DECISION (sammanfattning)

- Critical -> besvarat i `DECISIONS.md` D1–D5 (alla 5 blockerande fragor stangda)
- Important -> reflekterat i `ARCHITECTURE.md` (`SandboxRunner`, `ReplayCursor`, `human_approved`-status)
- Nice-to-have -> loggat i `OPEN_QUESTIONS.md` Q-NICE-1, Q-NICE-2

## Self-eval mot compound-agent-system upgrade-spec

| Spec | Krav | Denna sessions resultat |
|---|---|---|
| P0 | Idea -> ledger task | PASS — `t-006` oppnad innan vidare arbete |
| P1 | Intake-task innan blockers besvaras | FAIL initialt -> korrigerat. Forsta tva rundorna vantade pa operator-svar. Korrigerat nar upgrade-spec lastes. |
| P2 | Defaults + proceed-policy per blocker | PASS round 2 — alla beslut i `DECISIONS.md` har strukturerad form |
| P3 | Ingen duplicerad output | PASS |
| P4 | Identitet separerad client/model/role | PARTIAL — dokumenterat i `DECISIONS.md` D8 men ledger har fortfarande `claude-opus-4.7` (P4-fix kraver harness-uppdatering) |
| P10 | 7 standardartefakter | PASS — alla skrivna under `t-006` DoD |

Detta dokument refereras fran `.agents/EVAL_FINDINGS_session_2026-04-30.md`.
