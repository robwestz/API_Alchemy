# OPEN_QUESTIONS — API Alchemy Engine

> Producerad 2026-04-30 av claude-opus-4.7 (planner-roll).
> Endast fragor som ar blockerande for Fas 1 eller saknar default ligger har.
> Fragor som har default men kan andras av operator listas under "nice-to-have".
> Alla critical fragor (Q1–Q5 fran tidigare) ar besvarade — se DECISIONS.md.

---

## Blockerande for Fas 1 (max 5)

### Q-FAS1-1 — Postgres hosting

**Fraga**: Hur kor vi Postgres i Fas 1?

- (a) Lokal docker-compose postgres (men D4 sa undvik Docker)
- (b) Lokal Postgres via Windows installer eller scoop
- (c) Neon free tier (cloud, branchable, 0.5GB)
- (d) Railway / Supabase

**Default-forslag**: (c) Neon free tier. Branching gor det enkelt att jobba per fas, gratis-tier rymmer Fas 1–3.

**Paverkar fas**: Fas 1 (smoke test maste hitta databasen).

**Proceed-policy**: planner-default ok om operator inte svarar innan Fas 1-start.

**Status**: blocking

---

### Q-FAS1-2 — Action-parity-test depth i Fas 1

**Fraga**: I Fas 1, hur djupt testar vi action parity?

- (a) Bara att TOOL_REGISTRY existerar och har >=1 entry
- (b) Att en frontend-stub renderar UI fran registry
- (c) Full e2e: klick i frontend -> primitive kor -> Lake-skrivning -> WebSocket -> UI uppdaterar

**Default-forslag**: (a) for Fas 1. (b) inforas i Fas 1.5 om operator vill. (c) ar Fas 6:s DoD.

**Paverkar fas**: Fas 1 DoD.

**Proceed-policy**: planner-default ok.

**Status**: blocking (avgor Fas 1 scope)

---

### Q-FAS1-3 — Frontend-stub i Fas 1

**Fraga**: Vad ar "frontend-stub" konkret?

- (a) Tom Next.js-app som visar "Hello world" och en lista projekt fran /api/projects
- (b) Plus en "tools" sida som listar alla TOOL_REGISTRY entries med deras schemas
- (c) Plus en WebSocket-listener som loggar events till console

**Default-forslag**: (a) + (c). (b) defer till Fas 6.

**Paverkar fas**: Fas 1.

**Proceed-policy**: planner-default ok.

**Status**: blocking

---

### Q-FAS1-4 — Skill-attribution till Fas 0-task

**Fraga**: t-006 har `WARN: no --skill declared`. Vilken skill ska tasken kopplas till?

- (a) `architecture-audit` (passar fas-arbete)
- (b) `200k-blueprint` (passar full project initialization)
- (c) Bygga ny skill `api-alchemy-bootstrap`

**Default-forslag**: (a) `architecture-audit`. Standard for Fas 0-typ-arbete.

**Paverkar fas**: Fas 0 ledger-housekeeping.

**Proceed-policy**: planner-default ok. Korrigeras innan t-006 markeras done.

**Status**: blocking (verifier kommer flagga vid task done)

---

### Q-FAS1-5 — Hooks ENFORCE eller WARN i Fas 1

**Fraga**: Ska COMPOUND_ENFORCE=1 sattas vid Fas 1-start eller skjutas till Fas 3?

- (a) Skjut till Fas 3 — Fas 1–2 ar low-stakes (manuell kod)
- (b) Aktivera direkt — battre att tata friction tidigt

**Default-forslag**: (a) — Fas 1–2 har inga LLM-genererade artefakter. ENFORCE blir kritisk i Fas 3 nar Engineer borjar generera kod.

**Paverkar fas**: Fas 1+ samt R16 i risk-register.

**Proceed-policy**: planner-default ok.

**Status**: blocking (mode-flag maste vara satt innan Fas 3 borjar)

---

## Nice-to-have (har default, kan andras av operator)

### Q-NICE-1 — Time-travel queries

**Fraga**: Ska vi exponera time-travel-queries (data som den sag ut 2026-04-12) som en primitive eller endast som en intern ReplayCursor?

**Default**: intern ReplayCursor i Fas 1, ingen UI-yta i Fas 6. Kan promoteras till primitive om operator anvander det >5 ganger.

**Paverkar**: Fas 6 UI scope.

**Status**: nice-to-have, defer

---

### Q-NICE-2 — Notebook-export

**Fraga**: Insights -> Jupyter-notebook med samma queries reproducerade.

**Default**: defer till framtida fas. Inte i Fas 1–7 scope.

**Status**: nice-to-have, defer

---

### Q-NICE-3 — Frontend-ramverk subval

**Fraga**: Next.js App Router eller Pages Router?

**Default**: App Router (modernare, server-components-friendly, 2026-stilen).

**Paverkar**: Fas 6.

**Status**: nice-to-have, planner-default

---

### Q-NICE-4 — Demo-domaner for Fas 7

**Fraga**: Vilka tre demo-domaner ska anvandas?

**Default-forslag fran startpaket**: Swedish companies, SEO SERP, Public transport.

**Alternativ**: Fintech (kopplar till North Star-exemplet), Real estate, E-commerce.

**Status**: nice-to-have, operator valjer vid Fas 7-start

---

## Status-sammanfattning for Fas 0-godkannande

- **Critical fragor (Q1–Q5)**: alla besvarade, se DECISIONS.md D1–D5.
- **Blockerande for Fas 1 (Q-FAS1-1 till 5)**: alla har planner-default; operator kan veto:a.
- **Nice-to-have**: 4 stycken, defer.

Fas 0 ar redo for operator-signoff.
