/**
 * Source tab — route /source.
 *
 * Sections:
 *   1. Header: title + description
 *   2. Ingest form: URL input (monospace) + Ingest button (placeholder in Fas 6a)
 *   3. Tools section: all agent_allowed && ui_visible tools as ToolButton cards
 *   4. Recent ingests: placeholder table (data in Fas 6b)
 *
 * Server component for data fetching (tools list via RSC).
 * Ingest form is a client island via SourceIngestForm.
 */

import { listTools } from "@/lib/api-client";
import { ToolButton } from "@/components/ToolButton";
import { SourceIngestForm } from "@/app/source/SourceIngestForm";
import type { ToolSpec } from "@/lib/types";

// ---------------------------------------------------------------------------
// Data fetching
// ---------------------------------------------------------------------------

async function fetchVisibleTools(): Promise<ToolSpec[]> {
  try {
    const registry = await listTools();
    return Object.values(registry).filter(
      (tool) => tool.agent_allowed && tool.ui_visible,
    );
  } catch {
    return [];
  }
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default async function SourcePage() {
  const tools = await fetchVisibleTools();

  return (
    <div className="p-6 space-y-8 max-w-4xl">
      {/* Header */}
      <div className="space-y-1">
        <h1 className="text-lg font-semibold text-foreground tracking-[-0.02em]">
          Source
        </h1>
        <p className="text-xs text-muted-foreground">
          Ingest data from URL, file, or pasted JSON. Normalised events are
          written to the Universal Data Lake.
        </p>
      </div>

      {/* Ingest form — client island */}
      <SourceIngestForm />

      {/* Tools section */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground/60">
            Tool Registry
          </h2>
          <span className="text-[10px] font-mono text-muted-foreground/40">
            {tools.length} tool{tools.length !== 1 ? "s" : ""} available
          </span>
        </div>

        {tools.length === 0 ? (
          <div className="rounded-lg border border-border bg-card p-6 text-center">
            <p className="text-xs text-muted-foreground/50">
              No tools available — backend may be offline or registry is empty.
            </p>
            <p className="text-[10px] font-mono text-muted-foreground/30 mt-1">
              GET /api/tools returned empty
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {tools.map((tool) => (
              <ToolButton key={tool.name} tool={tool} />
            ))}
          </div>
        )}
      </div>

      {/* Recent ingests — placeholder */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground/60">
            Recent Ingests
          </h2>
          <span className="text-[10px] font-mono text-muted-foreground/40">
            Fas 6b
          </span>
        </div>
        <div className="rounded-lg border border-border overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border bg-muted/30">
                <th className="text-left px-4 py-2 font-medium text-muted-foreground">
                  Source
                </th>
                <th className="text-left px-4 py-2 font-medium text-muted-foreground">
                  Status
                </th>
                <th className="text-left px-4 py-2 font-medium text-muted-foreground font-mono">
                  Records
                </th>
                <th className="text-left px-4 py-2 font-medium text-muted-foreground">
                  Ingested
                </th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td
                  colSpan={4}
                  className="px-4 py-6 text-center text-muted-foreground/40 text-[11px]"
                >
                  No ingests yet. Submit a URL above to get started.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
