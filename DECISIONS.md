# DECISIONS — API Alchemy Engine

> Beslutslogg för Fas 0. Format följer compound-agent-system upgrade-spec P2:
> varje beslut har **fråga, varför det spelar roll, vald default, konsekvens, alternativ, proceed-policy**.
> Datum: 2026-04-30. Operatör: human-robin. Planner: claude-opus-4.7.

---

## D1 — Repo-target och git-strategi

**Fråga**: Var byggs maskinen, hur isoleras den från harness?

**Varför det spelar roll**: avgör om `.agents/` ledger delas med andra projekt eller dupliceras; avgör git-historik och pushability.

**Val**: Subdir under befintlig workspace (`C:\Users\robin\Videos\api_wrapper\api-alchemy-engine\`) med eget `git init`. `.gitignore` exkluderar `.agents/`, `.claude/`, `.codex/`, `.omc/` så harness aldrig commit:as.

**Konsekvens**:
- Harness ledger lever i parent `api_wrapper/` — alla build-time tasks (Fas 0–7) loggas där
- Produkt-repo är fristående, kan eventuellt push:as till GitHub utan harness-läckage
- Single git-historik per projekt (ren commit-log)

**Alternativ**: separat `~/Videos/api-alchemy-engine/` på samma nivå som `api_wrapper/`. Förkastat — bryter naturlig gruppering och kräver ny harness-bootstrap.

**Proceed-policy**: bekräftat av operatör.

---

## D2 — Adapter Registry scope

**Fråga**: Är det globalt (delat mellan alla projekt) eller per-projekt (isolerat)?

**Varför det spelar roll**: avgör om "compounding" är på riktigt — om en adapter byggd i projekt A kan återanvändas i projekt B utan ny generering.

**Val**: **Globalt registry med per-projekt-aktivering**.
- Adapter-manifest lagras i Lake (machine-wide tabell `adapter_manifests`)
- Genererad adapter-kod ligger i `adapters/<name>/v<n>/`
- Per projekt finns en `project_adapters`-tabell som länkar projekt-id till aktiva adapter-versioner (pinning)

**Konsekvens**:
- Cross-project lärande funkar — Scout kan upptäcka att en adapter redan finns
- Buggig adapter kan påverka flera projekt → mitigeras av per-projekt versions-pinning
- Kräver migrationspolicy när schema ändras (täcks av D7)

**Alternativ**: per-projekt isolerat. Förkastat — bryter compounding-löftet.

**Proceed-policy**: bekräftat av operatör.

---

## D3 — Secrets-hantering

**Fråga**: Hur hanteras API-keys för paid APIs som Scout/Engineer hittar?

**Varför det spelar roll**: säkerhet (R1), ergonomi, portabilitet.

**Val**: **Best practice med Doppler** (eller likvärdig vault) som primär; lokal `secrets.toml` per projekt som offline-fallback. `BaseAdapter` exponerar `secrets: SecretsResolver`-interface som abstraherar bort backend.
- `SecretsResolver` har implementation `DopplerResolver` (online) och `LocalTomlResolver` (offline)
- Adapter-kod aldrig läser env-vars direkt; alltid via resolver
- Sandbox-environment får aldrig hela vault — endast den specifika key som adaptern deklarerat behov av i sitt manifest

**Konsekvens**:
- Doppler-konto krävs för paid-API-bench i Fas 5 (kan skjutas till Fas 5)
- Ingen plain-text key i git eller logs
- Code review av Engineer-genererad adapter måste verifiera exakta keys, inte wildcard

**Alternativ**:
- (a) maskin vägrar paid → förkastat (begränsar nytta)
- (b) per-projekt prompt → behållet som UI-flöde ovanpå vault
- (c) global `.env` → förkastat som default men kvar som `LocalTomlResolver` fallback

**Proceed-policy**: bekräftat av operatör.

---

## D4 — Sandbox-strategi för auto-genererad adapter-kod

**Fråga**: Var och hur körs auto-genererad adapter-kod säkert?

**Varför det spelar roll**: R1 (skadlig kod / data-läckage). Operatör har Docker-friktion.

**Val**: **E2B free tier som primär** (cloud-sandbox, isolerad container, network-policy default `none`, opt-in per anrop). **GitHub Codespaces (90h/mån via Education Pack)** som fallback. Ingen lokal Docker eller WSL-setup krävs.

**Sandbox-interface**: `SandboxRunner` (i `interfaces/__init__.py`) abstraherar backend. Implementations:
- `E2BSandboxRunner` (default)
- `CodespacesSandboxRunner` (fallback)
- `LocalProcessSandboxRunner` (kräver explicit `--unsafe-local`-flag)

**Human-in-the-loop**: även när sandbox returnerar grönt visas manifest-diff + kod-preview för operatör innan adapter får göra första nätverksanrop mot riktig API. Status-sekvens: `generated` → `sandbox_passed` → `human_approved` → `active`.

**Konsekvens**:
- Beroende av extern tjänst (E2B) → Codespaces fallback
- Cloud-roundtrip kostar ~1–5s per sandbox-körning
- Inga Docker-installationer på din maskin

**Alternativ**:
- WSL2 + bubblewrap → förkastat
- Lokal Docker → förkastat

**Proceed-policy**: bekräftat av operatör.

---

## D5 — Tenancy-modell

**Fråga**: Single-user eller multi-tenant?

**Varför det spelar roll**: påverkar gateway-auth, projekt-isolation, cost-cap-segmentering.

**Val**: **Single-user, no auth, projekt-segmenterad state**.
- Gateway lyssnar på `localhost` only
- Lake-tabeller har `project_id`-kolumn överallt
- `cost_ledger` aggregeras per projekt
- Ingen `users`-tabell, ingen RBAC, ingen JWT
- Multi-tenant hardening = framtida task

**Konsekvens**: snabbare bygge, mindre yta att säkra. Om maskinen senare exponeras kräver det auth-lager + isolations-audit (separat fas).

**Alternativ**: full multi-tenant från dag 1. Förkastat — premature complexity.

**Proceed-policy**: bekräftat av operatör.

---

## D6 — Byggsekvens (avvikelse-fråga från GAP SCAN)

**Fråga**: Tool Registry införs i Fas 1 (planner-rekommendation) eller i Fas 6 (per startpaket)?

**Val**: **Tool Registry införs i Fas 1**, med uttrycklig signering.

**Operatörs uppdatering 2026-04-30**: operatör instruerade följa startpaketets struktur snarare än planner-deviationen. Tolkning: action parity-mekanismen får införas i Fas 1 (eftersom den är arkitekturell, inte feature). UI-konsumtion av registret hör till Fas 6.

**Konsekvens**: Fas 1 levererar `ToolSpec` Pydantic-klass + `tool_registry: dict[str, ToolSpec]` + minst en `tool_call` registrerad. Fas 6 lägger UI ovanpå.

**Alternativ**: skjuta hela Tool Registry till Fas 6. Förkastat — då måste Fas 2–5 refaktorieras retroaktivt.

**Proceed-policy**: planner-default; operatör kan veto:a vid Fas 0-signoff.

---

## D7 — Schema-evolution och adapter-versioning

**Fråga**: När en publik API släpper v2 och Pydantic-schema ändras, hur väljer Lake mellan v1/v2?

**Val**: **Manifest-driven versionering med per-projekt-pinning**.
- Varje adapter-version har `manifest.json`: `{name, version, schema_hash, doc_url, generated_at, model_used, prompts_used}`
- Lake `records` taggar varje record med `adapter_version`
- Projekt pinnar specifik version via `project_adapters`; Self-Repair föreslår uppgradering men kräver operatör-godkännande
- Replay-mode filtrerar på `adapter_version` för exakt reproducering

**Konsekvens**: lite mer schema-tax, mycket reproducibility.

**Alternativ**: senast-vinner. Förkastat — bryter reproducibility.

**Proceed-policy**: planner-default. Reflekteras i `interfaces/__init__.py` (BaseAdapter har `version: str` och `schema_hash: str`).

---

## D8 — Identity-modell (per upgrade-spec P4)

**Fråga**: Hur skiljer ledgern mellan client/model/role/session/ledger_id?

**Val**: **Normaliserad identity-schema**:
- `client`: claude-code | codex-cli | cursor | ...
- `model`: opus-4.7 | sonnet-4.6 | gpt-5-codex | ...
- `role`: planner | executor | reviewer | verifier | operator
- `ledger_agent_id`: kort stabil id (ex opus-planner, sonnet-exec-3)
- `session_id`: UUID per session
- `display_name`: human-readable

För denna session: client=claude-code, model=opus-4.7, role=planner+verifier, ledger_agent_id=opus-planner, display_name="Opus Planner". Befintlig signering är `claude-opus-4.7` (legacy från P4-violation); rättas i en framtida `agent-activate`-flow.

**Konsekvens**: framtida tasks får tydlig audit-trail.

**Alternativ**: fortsätt med blandade strängar. Förkastat.

**Proceed-policy**: planner-default; ej blockerande för Fas 0 produktion.

---

## Beslut som inte är låsta (öppna frågor → `OPEN_QUESTIONS.md`)

- D9: Demo-domäner för Fas 7 dogfood — operatör väljer vid Fas 7-start
- D10: Frontend-ramverk inom Next.js — App Router vs Pages Router (planner-default: App Router)
- D11: Postgres hosting i Fas 1 — lokal Docker-postgres vs Neon vs Railway (planner-default: Neon free tier; verifiera mot operatör)
