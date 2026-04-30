-- 001_initial.sql — API Alchemy Engine Universal Data Lake
-- Postgres schema per ARCHITECTURE.md sektion 1.
-- Kör: psql $DATABASE_URL -f packages/lake/migrations/001_initial.sql
-- Idempotent: använder IF NOT EXISTS överallt.

-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------

CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- gen_random_uuid()


-- ---------------------------------------------------------------------------
-- projects
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS projects (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT        NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    daily_cap_usd   NUMERIC(12,6) NOT NULL DEFAULT 5.0,
    monthly_cap_usd NUMERIC(12,6) NOT NULL DEFAULT 50.0
);

CREATE INDEX IF NOT EXISTS idx_projects_created_at ON projects (created_at);


-- ---------------------------------------------------------------------------
-- events  (immutable append-only log)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS events (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id  UUID        NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    kind        TEXT        NOT NULL,
    payload     JSONB       NOT NULL DEFAULT '{}',
    ts          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_events_project_id ON events (project_id);
CREATE INDEX IF NOT EXISTS idx_events_kind       ON events (kind);
CREATE INDEX IF NOT EXISTS idx_events_ts         ON events (ts);


-- ---------------------------------------------------------------------------
-- records  (JSONB swallows any API response; lineage per rad)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS records (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID        NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    adapter_name    TEXT        NOT NULL,
    adapter_version TEXT        NOT NULL,
    schema_hash     TEXT        NOT NULL,
    payload         JSONB       NOT NULL DEFAULT '{}',
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    lineage         JSONB       NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_records_project_id      ON records (project_id);
CREATE INDEX IF NOT EXISTS idx_records_adapter_name    ON records (adapter_name);
CREATE INDEX IF NOT EXISTS idx_records_adapter_version ON records (adapter_version);
CREATE INDEX IF NOT EXISTS idx_records_fetched_at      ON records (fetched_at);


-- ---------------------------------------------------------------------------
-- agent_actions  (varje agent-steg loggas)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS agent_actions (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id    UUID        NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    agent_name    TEXT        NOT NULL,
    action        TEXT        NOT NULL,
    input         JSONB       NOT NULL DEFAULT '{}',
    output        JSONB       NOT NULL DEFAULT '{}',
    denied_reason TEXT,
    ts            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_actions_project_id ON agent_actions (project_id);
CREATE INDEX IF NOT EXISTS idx_agent_actions_agent_name ON agent_actions (agent_name);
CREATE INDEX IF NOT EXISTS idx_agent_actions_ts         ON agent_actions (ts);


-- ---------------------------------------------------------------------------
-- tool_calls_log  (reproducibility: prompt+model+seed+hashes)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS tool_calls_log (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id  UUID        NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    tool_name   TEXT        NOT NULL,
    prompt      TEXT,
    model       TEXT        NOT NULL,
    temperature NUMERIC(4,3),
    seed        INTEGER,
    input_hash  TEXT,
    output_hash TEXT,
    ts          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tool_calls_log_project_id ON tool_calls_log (project_id);
CREATE INDEX IF NOT EXISTS idx_tool_calls_log_tool_name  ON tool_calls_log (tool_name);
CREATE INDEX IF NOT EXISTS idx_tool_calls_log_ts         ON tool_calls_log (ts);


-- ---------------------------------------------------------------------------
-- arena_scores  (Judge-agent benchmark per adapter-version)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS arena_scores (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    adapter_name        TEXT        NOT NULL,
    adapter_version     TEXT        NOT NULL,
    latency_p50_ms      NUMERIC(10,2) NOT NULL,
    latency_p95_ms      NUMERIC(10,2) NOT NULL,
    fields_per_response INTEGER     NOT NULL,
    cost_per_1k_usd     NUMERIC(12,6) NOT NULL,
    dx_score            NUMERIC(5,3)  NOT NULL,
    measured_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_arena_scores_adapter_name    ON arena_scores (adapter_name);
CREATE INDEX IF NOT EXISTS idx_arena_scores_adapter_version ON arena_scores (adapter_version);
CREATE INDEX IF NOT EXISTS idx_arena_scores_measured_at     ON arena_scores (measured_at);


-- ---------------------------------------------------------------------------
-- adapter_manifests  (globalt registry per D2)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS adapter_manifests (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name             TEXT        NOT NULL,
    version          TEXT        NOT NULL,
    schema_hash      TEXT        NOT NULL,
    doc_url          TEXT        NOT NULL,
    generated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    model_used       TEXT        NOT NULL,
    prompts_used     JSONB       NOT NULL DEFAULT '[]',
    secrets_required JSONB       NOT NULL DEFAULT '[]',
    status           TEXT        NOT NULL DEFAULT 'generated',
    UNIQUE (name, version)
);

CREATE INDEX IF NOT EXISTS idx_adapter_manifests_name   ON adapter_manifests (name);
CREATE INDEX IF NOT EXISTS idx_adapter_manifests_status ON adapter_manifests (status);


-- ---------------------------------------------------------------------------
-- discovery_index  (Scout-agent output per projekt)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS discovery_index (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id   UUID        NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    domain       TEXT        NOT NULL,
    candidates   JSONB       NOT NULL DEFAULT '[]',
    cost_usd     NUMERIC(12,6) NOT NULL DEFAULT 0,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_discovery_index_project_id ON discovery_index (project_id);
CREATE INDEX IF NOT EXISTS idx_discovery_index_domain     ON discovery_index (domain);


-- ---------------------------------------------------------------------------
-- cost_ledger  (per LLM-anrop, per projekt — ARCHITECTURE.md sektion 6)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS cost_ledger (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID        NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    agent_id   TEXT        NOT NULL,
    model      TEXT        NOT NULL,
    tokens_in  INTEGER     NOT NULL DEFAULT 0,
    tokens_out INTEGER     NOT NULL DEFAULT 0,
    cost_usd   NUMERIC(12,6) NOT NULL DEFAULT 0,
    ts         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cost_ledger_project_id ON cost_ledger (project_id);
CREATE INDEX IF NOT EXISTS idx_cost_ledger_agent_id   ON cost_ledger (agent_id);
CREATE INDEX IF NOT EXISTS idx_cost_ledger_ts         ON cost_ledger (ts);


-- ---------------------------------------------------------------------------
-- project_adapters  (per-projekt versions-pinning per D2)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS project_adapters (
    project_id     UUID        NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    adapter_name   TEXT        NOT NULL,
    pinned_version TEXT        NOT NULL,
    activated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, adapter_name)
);

CREATE INDEX IF NOT EXISTS idx_project_adapters_adapter_name ON project_adapters (adapter_name);
