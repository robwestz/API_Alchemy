# ENV_SETUP — Postgres-konfiguration

API Alchemy Engine anvander Postgres som Universal Data Lake.
Standard i Fas 1 ar Neon free tier (per DECISIONS.md D11).
Ingen Docker kravs (D4: operatoren har Docker-friktion).

---

## Alternativ A — Neon free tier (rekommenderat)

Neon ar en serverless Postgres-tjanst med generost free tier och
inbyggd branching. Passar perfekt for Fas 1 utan lokal infrastruktur.

1. Skapa konto pa [neon.tech](https://neon.tech) (gratis, inget kreditkort kravs)
2. Skapa ett nytt projekt (ex. `api-alchemy-engine`)
3. Kopiera connection string fran Neon dashboard:
   - Format: `postgres://user:password@ep-xxx.region.aws.neon.tech/neondb?sslmode=require`
4. Klistra in i `.env`:
   ```
   DATABASE_URL=postgres://user:password@ep-xxx.region.aws.neon.tech/neondb?sslmode=require
   ```
5. Kor migrering:
   ```bash
   psql $DATABASE_URL -f packages/lake/migrations/001_initial.sql
   ```
6. Verifiera:
   ```bash
   psql $DATABASE_URL -c "\dt"
   ```
   Du ska se tio tabeller: projects, events, records, agent_actions,
   tool_calls_log, arena_scores, adapter_manifests, discovery_index,
   cost_ledger, project_adapters.

---

## Alternativ B — Lokal Postgres via Scoop (Windows)

Om du foredrar lokal installation utan molnberoende:

1. Installera Scoop om det saknas:
   ```powershell
   Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
   irm get.scoop.sh | iex
   ```
2. Installera Postgres:
   ```powershell
   scoop install postgresql
   ```
3. Initiera och starta:
   ```powershell
   pg_ctl initdb -D "$env:USERPROFILE\postgres-data"
   pg_ctl start -D "$env:USERPROFILE\postgres-data" -l "$env:USERPROFILE\postgres.log"
   ```
4. Skapa databas:
   ```powershell
   createdb api_alchemy
   ```
5. Satt DSN i `.env`:
   ```
   DATABASE_URL=postgres://localhost/api_alchemy
   ```
6. Kor migrering:
   ```powershell
   psql $env:DATABASE_URL -f packages/lake/migrations/001_initial.sql
   ```

---

## .env-fil

Kopiera mallen och fyll i dina varden:

```bash
cp .env.example .env
```

Se `.env.example` for alla tillgangliga variabler.

---

## Integrationstester

For att kora integrationstesterna mot en riktig DB, satt:

```bash
TEST_DATABASE_URL=postgres://user:pass@host/testdb
pytest tests/integration/ -v -m integration
```

Testerna skapar tabellerna automatiskt via `001_initial.sql` och
hoppar over om `TEST_DATABASE_URL` ej ar satt.
