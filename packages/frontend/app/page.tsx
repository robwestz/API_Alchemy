/**
 * Dashboard — default route (/).
 *
 * Sections:
 *   1. Hero: title + tagline (informative, not marketing)
 *   2. Status grid: backend health, project count, tool count, current task
 *   3. Quick-action cards: New project, Browse tools, Open project
 *   4. Recent projects table (if any)
 *   5. Registered tools badge list
 *
 * Server component — all data fetched at render time (RSC, no "use client").
 * Graceful degradation when backend is offline.
 */

import Link from "next/link";

// Force dynamic rendering — page fetches from backend at request time, not build time
export const dynamic = "force-dynamic";

import {
  CheckCircle,
  XCircle,
  Database,
  Zap,
  FolderPlus,
  FolderOpen,
} from "lucide-react";
import { getHealth, listProjects, listTools } from "@/lib/api-client";
import type { HealthResponse, Project, ToolRegistry } from "@/lib/types";

// ---------------------------------------------------------------------------
// Data fetching (parallel, graceful degradation)
// ---------------------------------------------------------------------------

async function fetchDashboardData(): Promise<{
  health: HealthResponse | null;
  projects: Project[];
  tools: ToolRegistry;
}> {
  const [healthResult, projectsResult, toolsResult] = await Promise.allSettled([
    getHealth(),
    listProjects(),
    listTools(),
  ]);

  return {
    health: healthResult.status === "fulfilled" ? healthResult.value : null,
    projects:
      projectsResult.status === "fulfilled" ? projectsResult.value : [],
    tools: toolsResult.status === "fulfilled" ? toolsResult.value : {},
  };
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function StatusCard({
  label,
  value,
  sub,
  online,
}: {
  label: string;
  value: string;
  sub?: string;
  online?: boolean;
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-4 flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/60">
          {label}
        </span>
        {online !== undefined &&
          (online ? (
            <CheckCircle className="h-3.5 w-3.5 text-primary" />
          ) : (
            <XCircle className="h-3.5 w-3.5 text-destructive" />
          ))}
      </div>
      <span className="text-2xl font-semibold tabular-nums text-foreground tracking-tight">
        {value}
      </span>
      {sub && (
        <span className="text-[11px] text-muted-foreground font-mono">
          {sub}
        </span>
      )}
    </div>
  );
}

function QuickActionCard({
  href,
  icon: Icon,
  title,
  description,
}: {
  href: string;
  icon: React.ElementType;
  title: string;
  description: string;
}) {
  return (
    <Link
      href={href}
      className="group rounded-lg border border-border bg-card p-4 flex flex-col gap-2 hover:border-primary/40 hover:bg-muted/30 transition-all duration-150"
    >
      <div className="flex items-center gap-2">
        <Icon className="h-4 w-4 text-muted-foreground group-hover:text-primary transition-colors" />
        <span className="text-sm font-medium text-foreground">{title}</span>
      </div>
      <p className="text-xs text-muted-foreground leading-relaxed">
        {description}
      </p>
    </Link>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default async function DashboardPage() {
  const { health, projects, tools } = await fetchDashboardData();

  const toolCount = Object.keys(tools).length;
  const visibleToolCount = Object.values(tools).filter(
    (t) => t.ui_visible,
  ).length;

  return (
    <div className="p-6 space-y-8 max-w-4xl">
      {/* Hero */}
      <div className="space-y-1.5">
        <h1 className="text-xl font-semibold text-foreground tracking-[-0.02em]">
          API Alchemy Engine
        </h1>
        <p className="text-sm text-muted-foreground leading-relaxed max-w-2xl">
          Autonom motor som tar en idé eller domän-uttryck och producerar en
          användbar dataprodukt — normaliserat schema, REST-API, insight-rapport
          och product brief — via en svärm av agenter över ett delat workspace.
        </p>
      </div>

      {/* Status grid */}
      <div>
        <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground/60 mb-3">
          System Status
        </h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatusCard
            label="Backend"
            value={health ? "Online" : "Offline"}
            sub={
              health
                ? `v${health.version}`
                : "localhost:8000 unreachable"
            }
            online={health !== null}
          />
          <StatusCard
            label="Projects"
            value={String(projects.length)}
            sub={
              projects.length === 0
                ? "no projects yet"
                : `${projects.length} workspace${projects.length !== 1 ? "s" : ""}`
            }
          />
          <StatusCard
            label="Tools"
            value={String(toolCount)}
            sub={`${visibleToolCount} ui-visible`}
          />
          <StatusCard
            label="Current Task"
            value="—"
            sub="task ledger: Fas 6b"
          />
        </div>
      </div>

      {/* Quick actions */}
      <div>
        <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground/60 mb-3">
          Quick Actions
        </h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <QuickActionCard
            href="/projects/new"
            icon={FolderPlus}
            title="New Project"
            description="Create a new workspace. Ingest a domain, URL, or paste JSON to start building a data product."
          />
          <QuickActionCard
            href="/source"
            icon={Database}
            title="Browse Tools"
            description="Explore all registered primitives in the Tool Registry. Execute tools directly from the UI."
          />
          <QuickActionCard
            href={
              projects[0] ? `/projects/${projects[0].id}` : "/projects/new"
            }
            icon={FolderOpen}
            title="Open Project"
            description={
              projects[0]
                ? `Continue with "${projects[0].name}"`
                : "No projects yet — create one to get started."
            }
          />
        </div>
      </div>

      {/* Recent projects table */}
      {projects.length > 0 && (
        <div>
          <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground/60 mb-3">
            Recent Projects
          </h2>
          <div className="rounded-lg border border-border overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border bg-muted/30">
                  <th className="text-left px-4 py-2 font-medium text-muted-foreground">
                    Name
                  </th>
                  <th className="text-left px-4 py-2 font-medium text-muted-foreground font-mono">
                    ID
                  </th>
                  <th className="text-left px-4 py-2 font-medium text-muted-foreground">
                    Created
                  </th>
                </tr>
              </thead>
              <tbody>
                {projects.slice(0, 5).map((project, i) => (
                  <tr
                    key={project.id}
                    className={`hover:bg-muted/20 transition-colors ${
                      i < Math.min(projects.length, 5) - 1
                        ? "border-b border-border/50"
                        : ""
                    }`}
                  >
                    <td className="px-4 py-2.5">
                      <Link
                        href={`/projects/${project.id}`}
                        className="text-foreground/80 hover:text-primary transition-colors"
                      >
                        {project.name}
                      </Link>
                    </td>
                    <td
                      className="px-4 py-2.5 font-mono text-muted-foreground/60 text-[10px]"
                      title={project.id}
                    >
                      {project.id.slice(0, 8)}&hellip;
                    </td>
                    <td className="px-4 py-2.5 text-muted-foreground tabular-nums">
                      {new Date(project.created_at).toLocaleDateString("sv-SE")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tool registry summary */}
      {toolCount > 0 && (
        <div>
          <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground/60 mb-3">
            Registered Tools
          </h2>
          <div className="flex flex-wrap gap-2">
            {Object.values(tools).map((tool) => (
              <span
                key={tool.name}
                className="inline-flex items-center gap-1.5 rounded-md border border-border bg-card px-2.5 py-1 text-[11px] font-mono text-foreground/70 hover:border-primary/40 transition-colors"
                title={tool.description}
              >
                {tool.agent_allowed && (
                  <Zap className="h-2.5 w-2.5 text-accent" />
                )}
                {tool.name}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
