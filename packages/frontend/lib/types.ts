/**
 * Frontend TypeScript types for API Alchemy Engine.
 *
 * These mirror Python types defined in:
 *   - packages/interfaces/__init__.py  (ToolSpec, AgentResult)
 *   - packages/lake/repository.py      (Project)
 *   - packages/gateway/main.py         (ToolListItem, /health response)
 *
 * Manual sync required until Fas 6b automates schema export.
 * Field names must stay in sync with Pydantic models.
 */

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------

/** Mirrors GET /health response. See gateway/main.py health() */
export interface HealthResponse {
  status: string;   // always "ok" when up
  version: string;  // e.g. "0.1.0"
}

// ---------------------------------------------------------------------------
// Tools (mirrors gateway ToolListItem + interfaces ToolSpec)
// ---------------------------------------------------------------------------

/**
 * Serializable representation of a ToolSpec.
 * Handler callable is stripped by gateway — only metadata returned.
 * Mirrors: packages/gateway/main.py ToolListItem
 *          packages/interfaces/__init__.py ToolSpec
 */
export interface ToolSpec {
  name: string;
  description: string;
  /** JSON Schema object for input validation */
  input_schema: Record<string, unknown>;
  /** JSON Schema object for output shape */
  output_schema: Record<string, unknown>;
  /** Whether agents may invoke this tool autonomously */
  agent_allowed: boolean;
  /** Whether to show this tool in the Lab UI */
  ui_visible: boolean;
  /** Optional component hint for Lab UI rendering (e.g. "StatusBadge") */
  ui_component: string | null;
}

/** Map of tool name -> ToolSpec — mirrors ToolRegistry dict[str, ToolSpec] */
export type ToolRegistry = Record<string, ToolSpec>;

// ---------------------------------------------------------------------------
// Projects (mirrors packages/lake/repository.py Project)
// ---------------------------------------------------------------------------

/**
 * A project workspace.
 * Mirrors: packages/lake/repository.py Project (Pydantic model)
 */
export interface Project {
  id: string;           // UUID as string
  name: string;
  created_at: string;   // ISO 8601 UTC, e.g. "2026-04-29T12:00:00Z"
}

// ---------------------------------------------------------------------------
// Activity Log events (WebSocket broadcast, Fas 6c)
// ---------------------------------------------------------------------------

/**
 * An agent activity event broadcast via WebSocket.
 * WebSocket topic: project:<id> — see gateway/main.py websocket_project()
 * Mirrors: packages/interfaces/__init__.py AgentResult (partial)
 */
export interface AgentEvent {
  id: string;           // UUID as string
  ts: string;           // ISO 8601 UTC timestamp
  agent_name: string;   // e.g. "Scout", "Engineer", "Judge"
  action: string;       // human-readable action description
  /** Full structured payload — unknown until narrowed */
  payload: unknown;
}

// ---------------------------------------------------------------------------
// UI state helpers
// ---------------------------------------------------------------------------

/** Generic async data state for loading/error/success pattern */
export type AsyncState<T> =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success"; data: T }
  | { status: "error"; error: string };
