/**
 * Type-safe API client for API Alchemy Engine gateway.
 *
 * All frontend fetch calls go through this module — never raw fetch() elsewhere.
 * Backend endpoints: packages/gateway/main.py
 * Default base: http://localhost:8000 (localhost-only per ARCHITECTURE.md D5)
 * Override via NEXT_PUBLIC_API_BASE env var.
 */

import type { HealthResponse, ToolRegistry, Project } from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/** Shared fetch wrapper with error handling and graceful degradation */
async function apiFetch<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const url = `${API_BASE}${path}`;
  let res: Response;

  try {
    res = await fetch(url, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...options?.headers,
      },
    });
  } catch (err) {
    // Network error — backend not running or unreachable
    throw new ApiError(
      0,
      `Cannot reach backend at ${API_BASE}. Is it running? (${String(err)})`,
    );
  }

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // ignore parse error, use statusText
    }
    throw new ApiError(res.status, detail);
  }

  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Error type
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** True when backend is simply not reachable (status 0) */
  get isOffline(): boolean {
    return this.status === 0;
  }
}

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------

/**
 * GET /health
 * Smoke-test — returns status + version. Used on dashboard status card.
 */
export async function getHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>("/health");
}

// ---------------------------------------------------------------------------
// Tools
// ---------------------------------------------------------------------------

/**
 * GET /api/tools
 * Returns all registered primitives (ToolRegistry without handlers).
 * Frontend renders ToolButton components from this data (action parity).
 */
export async function listTools(): Promise<ToolRegistry> {
  return apiFetch<ToolRegistry>("/api/tools");
}

// ---------------------------------------------------------------------------
// Projects
// ---------------------------------------------------------------------------

/**
 * GET /api/projects
 * Returns all projects, newest first.
 */
export async function listProjects(): Promise<Project[]> {
  return apiFetch<Project[]>("/api/projects");
}

/**
 * POST /api/projects
 * Creates a new project workspace. Returns the created Project with UUID.
 */
export async function createProject(name: string): Promise<Project> {
  return apiFetch<Project>("/api/projects", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

// ---------------------------------------------------------------------------
// Tool execution
// ---------------------------------------------------------------------------

/**
 * POST /api/tools/{name}
 * Executes a registered primitive. Same handler agents use (action parity).
 * Input is validated by gateway against ToolSpec.input_schema.
 * Returns unknown — caller must narrow based on tool's output_schema.
 */
export async function executeTool(
  name: string,
  input: unknown,
): Promise<unknown> {
  return apiFetch<unknown>(`/api/tools/${encodeURIComponent(name)}`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}
