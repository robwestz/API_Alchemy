# RISK_REGISTER — API Alchemy Engine

> Utokat fran startpaket sektion 8. Datum: 2026-04-30. Planner: claude-opus-4.7.
> Granskat av Chief Skeptic-roll (intern). Mitigeringar refererar till DECISIONS.md.

---

## Risk-tabell

| # | Risk | Sannolikhet | Allvar | Mitigering | Trigger fas | Status |
|---|---|---|---|---|---|---|
| R1 | Auto-genererad adapter-kod gor skadliga natverksanrop / lacker secrets | Medel | Hog | E2B sandbox network=none default (D4). Secrets per-adapter via SecretsResolver (D3). Human-in-the-loop pa human_approved-status innan main-process. | Fas 3 | open |
| R2 | Scout hallucinerar API-URL:er som inte finns | Hog | Medel | Engineer maste lyckas hamta doc-URL innan adapter-generering. DoD-test i Fas 4. | Fas 4 | open |
| R3 | LLM-kostnader skenar vid agent-loopar | Medel | Medel | cost_ledger per-projekt (ARCHITECTURE.md sektion 6). Daily/monthly cap. Graceful degrade vid 100%. | Fas 1+ | open |
| R4 | Pydantic-schema drift nar API andras -> Self-Repair fastnar i loop | Medel | Medel | Max retry-count pa Engineer-regen (3 forsok). Eskalera till operator. | Fas 3 | open |
| R5 | Action parity bryts nar nya features laggs till | Medel | Medel | CI-check tests/test_action_parity.py. Bryter bygget om paritet brutits. Inforas i Fas 1 (D6). | Fas 1+ | open |
| R6 | Premature optimization (Rust for tjanster som inte ar flaskhals) | Lag | Lag | Profilera forst, byt ut sen. | Fas 2+ | accepted |
| R7 | Adapter-katalogen blir spaghetti nar 50+ API:er registrerats | Medel | Medel | Standardiserad adapters/<name>/v<n>/-mappstruktur. Manifest-driven via adapter_manifests-tabell. | Fas 3 | open |
| R8 | Leaderboard-poang blir politiska (vad ar bast?) | Lag | Lag | Vikter konfigurerbara per projekt. Transparent score-formel. | Fas 5 | open |
| R9 | Vendor lock-in via specifik LLM | Lag | Lag | LiteLLM-abstraktion obligatorisk. Modellnamn endast i config. | Fas 1+ | mitigated |
| R10 | Bygger en cool plattform men producerar aldrig en produkt | Hog | Hog | Fas 7 = obligatorisk dogfood mot 3 demo-domaner. | Fas 7 | open |
| R11 | E2B free tier rate-limit / downtime stoppar Engineer-loop | Medel | Medel | Codespaces fallback (Education Pack 90h/man). Local fallback med --unsafe-local-flag. | Fas 3 | open |
| R12 | Globalt adapter-registry: en buggig adapter pavekas alla projekt | Medel | Medel | Per-projekt versions-pinning via project_adapters-tabell (D2). Operator kontrollerar uppgradering. | Fas 3 | mitigated |
| R13 | Replay-mode bryts nar adapter-version uppgraderas (gammal kod borta) | Lag | Hog | Adapter-kod sparas i adapters/<name>/v<n>/ for ALLA versioner. Manifest har model_used + prompts_used. | Fas 3 | open |
| R14 | Single-user antagandet bryts nar maskinen ska delas senare | Lag | Hog | Gateway ar tunn FastAPI-middleware. project_id-isolation finns redan (D5). Auth-lager kan slangas pa. | Future | accepted |
| R15 | Doppler-konto-setup tar tid och blockerar Fas 5 | Medel | Lag | LocalTomlResolver fungerar offline. Doppler-setup deferras till Fas 5-start. | Fas 5 | open |
| R16 | Operator forutsater att harness skydder mot sakerhets-fail medan WARN-mode endast loggar | Medel | Hog | DoD-task.mjs-output sager "Mode: WARN (advisory)". Aktivera COMPOUND_ENFORCE=1 innan Fas 3. | Fas 3 | open |
| R17 | Subagent-loopar (Sonnet via Task-tool) producerar kod som ej foljer arkitektur-principer | Medel | Medel | Verifier-rollen kor DoD-checks. Code review av Lead Architect for arkitektur-paverkande PRs. Linter. | Fas 1+ | open |
| R18 | Long-session context decay nar bygget paverkar 8 faser | Hog | Medel | CONTEXT REFRESH mekanism 3 vid varje fas-overgang. COMPOUND_LOG.md halls live. Handoff-bridge for sessioner > N timmar. | Continuous | open |

---

## Skeptic-prioritering (3 hogsta riskerna)

1. **R10** — vagrar dogfood-disciplin. Mitigering: Fas 7 ar inte forhandlingsbar. Operator far inte signera maskinen "klar" forrn 3 oberoende dogfood-korningar levererat full kedja.
2. **R1** — sandbox-fail med skadlig adapter-kod. Mitigering: E2B network=none + manifest-deklarerade secrets + human_approved-status. Kombinationen halls obligatorisk.
3. **R16** — falsk trygghet i WARN-mode. Mitigering: hooks i .agents/PROTOCOL.md ska tvinga ENFORCE-mode innan Fas 3. Tills dess ar adapter-kod-genererings-arbete blockerat.

---

## Risk-uppdatering

Detta dokument uppdateras vid varje fas-borjan via Skeptic-pass. Nya risker laggs som R19, R20, ... Risk som mitigeras far status `mitigated`. Risk som accepteras far status `accepted` med motivering.
