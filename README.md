# API Alchemy Engine

> Autonom motor som tar en ide eller doman-uttryck och producerar en anvandbar dataprodukt via en svarm av agenter over ett delat workspace — samtidigt som den bygger pa sig sjalv genom att lara sig nya API-integrationer.

Se [PROJECT_BRIEF.md](PROJECT_BRIEF.md) for fullstandig beskrivning och [ARCHITECTURE.md](ARCHITECTURE.md) for arkitektur-stack.

## Snabbstart

```bash
# 1. Installera beroenden (Python 3.11+)
pip install -e ".[dev]"

# 2. Konfigurera miljo
cp .env.example .env
# Redigera .env och lagg in DATABASE_URL (se ENV_SETUP.md)

# 3. Kor databas-migrering
psql $DATABASE_URL -f packages/lake/migrations/001_initial.sql

# 4. Starta gateway
uvicorn packages.gateway.main:app --host 127.0.0.1 --port 8000 --reload
```

Gateway ar nu tillganglig pa `http://127.0.0.1:8000`.

## Endpoints

| Metod | Path | Beskrivning |
|-------|------|-------------|
| GET | `/health` | Systemstatus |
| GET | `/api/tools` | Lista registrerade primitives (Tool Registry) |
| POST | `/api/tools/{name}` | Exekvera en primitive |
| POST | `/api/projects` | Skapa projekt |
| GET | `/api/projects` | Lista projekt |
| GET | `/api/projects/{id}` | Hamta specifikt projekt |
| WS | `/ws/projects/{id}` | WebSocket event-strom per projekt |

Interaktiv API-dokumentation: `http://127.0.0.1:8000/docs`

## Tester

```bash
# Unit + action parity (ingen DB kravs)
pytest tests/test_action_parity.py -v

# Integrationstester (kraver TEST_DATABASE_URL i miljon)
TEST_DATABASE_URL=postgres://user:pass@host/testdb pytest tests/integration/ -v -m integration
```

## Dokumentation

| Fil | Innehall |
|-----|----------|
| [PROJECT_BRIEF.md](PROJECT_BRIEF.md) | North star, kapacitetskarta, anti-goals |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Lager-stack, tre self-loops, action parity, kostnadskontroll |
| [DECISIONS.md](DECISIONS.md) | D1-D8: arkitektur-beslut med rationale |
| [PHASE_PLAN.md](PHASE_PLAN.md) | Fas 1-7 med DoD per fas |
| [ENV_SETUP.md](ENV_SETUP.md) | Postgres-setup (Neon / lokal) |

## Fas-status

- **Fas 0** — Gap Scan & Architecture Forge (klar)
- **Fas 1** — Skeleton + Universal Data Lake + Tool Registry (denna leverans)
- Fas 2-7 — se PHASE_PLAN.md
