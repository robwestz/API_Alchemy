/**
 * Sidebar — left navigation panel (240px fixed width).
 *
 * Sections:
 *   1. Logo + online status dot
 *   2. Workspace selector (placeholder "default" for Fas 6a)
 *   3. Projects — fetched from GET /api/projects
 *   4. Navigation — tabs (Source active, others disabled in Fas 6a)
 *   5. Settings — ENV mode indicator at bottom
 *
 * Server component — fetches project list on render (RSC, no "use client").
 * Navigation links use Next.js <Link> for client-side routing.
 */

import Link from "next/link";
import {
  Database,
  FileJson,
  BarChart2,
  FileCode,
  FileText,
  ScrollText,
  Swords,
  Layers,
  Settings,
  FolderOpen,
  Plus,
} from "lucide-react";
import { listProjects } from "@/lib/api-client";
import type { Project } from "@/lib/types";

// ---------------------------------------------------------------------------
// Navigation tab definitions
// ---------------------------------------------------------------------------

const NAV_TABS = [
  { label: "Source",    href: "/source",    icon: Database,  active: true  },
  { label: "Dataset",   href: "/dataset",   icon: Layers,    active: false },
  { label: "Schema",    href: "/schema",    icon: FileJson,  active: false },
  { label: "Insights",  href: "/insights",  icon: BarChart2, active: false },
  { label: "API Spec",  href: "/api-spec",  icon: FileCode,  active: false },
  { label: "Brief",     href: "/brief",     icon: FileText,  active: false },
  { label: "Agent Log", href: "/agent-log", icon: ScrollText,active: false },
  { label: "Arena",     href: "/arena",     icon: Swords,    active: false },
] as const;

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="px-3 py-1.5">
      <span className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/50">
        {children}
      </span>
    </div>
  );
}

async function ProjectList() {
  let projects: Project[] = [];
  let error = false;

  try {
    projects = await listProjects();
  } catch {
    error = true;
  }

  if (error) {
    return (
      <div className="px-3 py-1.5">
        <span className="text-[10px] text-destructive/70 font-mono">
          backend offline
        </span>
      </div>
    );
  }

  if (projects.length === 0) {
    return (
      <div className="px-3 py-1.5">
        <span className="text-[10px] text-muted-foreground/40">
          No projects yet
        </span>
      </div>
    );
  }

  return (
    <ul className="space-y-0.5">
      {projects.map((project) => (
        <li key={project.id}>
          <Link
            href={`/projects/${project.id}`}
            className="flex items-center gap-2 rounded-md px-3 py-1.5 text-xs text-muted-foreground hover:bg-muted hover:text-foreground transition-colors group"
            title={`ID: ${project.id}\nCreated: ${project.created_at}`}
          >
            <FolderOpen className="h-3 w-3 shrink-0 opacity-50 group-hover:opacity-80" />
            <span className="truncate">{project.name}</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

// ---------------------------------------------------------------------------
// Main Sidebar component
// ---------------------------------------------------------------------------

export async function Sidebar() {
  return (
    <nav
      className="flex flex-col border-r border-border bg-card w-60 shrink-0 overflow-y-auto overflow-x-hidden"
      aria-label="Main navigation"
    >
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-4 py-3.5 border-b border-border shrink-0">
        <div className="relative flex h-2 w-2 shrink-0">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-60" />
          <span className="relative inline-flex rounded-full h-2 w-2 bg-primary" />
        </div>
        <span className="font-semibold text-sm tracking-tight text-foreground">
          API Alchemy
        </span>
      </div>

      {/* Workspace selector */}
      <div className="px-3 py-2.5 border-b border-border shrink-0">
        <div className="flex items-center justify-between rounded-md border border-border bg-muted/50 px-2.5 py-1.5">
          <span className="text-xs text-muted-foreground">Workspace</span>
          <span className="text-xs font-mono text-foreground/70">default</span>
        </div>
      </div>

      <div className="flex flex-col gap-1 flex-1 py-2">
        {/* Projects */}
        <div>
          <div className="flex items-center justify-between pr-2">
            <SectionLabel>Projects</SectionLabel>
            <Link
              href="/projects/new"
              className="p-1 rounded text-muted-foreground/50 hover:text-foreground hover:bg-muted transition-colors"
              title="New project"
              aria-label="New project"
            >
              <Plus className="h-3 w-3" />
            </Link>
          </div>
          <ProjectList />
        </div>

        {/* Navigation */}
        <div className="mt-3">
          <SectionLabel>Navigation</SectionLabel>
          <ul className="space-y-0.5 mt-0.5">
            {NAV_TABS.map((tab) => {
              const Icon = tab.icon;
              return (
                <li key={tab.href}>
                  {tab.active ? (
                    <Link
                      href={tab.href}
                      className="flex items-center gap-2 rounded-md px-3 py-1.5 text-xs text-foreground/80 hover:bg-muted hover:text-foreground transition-colors"
                    >
                      <Icon className="h-3.5 w-3.5 shrink-0 text-primary" />
                      {tab.label}
                    </Link>
                  ) : (
                    <span
                      className="flex items-center gap-2 rounded-md px-3 py-1.5 text-xs text-muted-foreground/35 cursor-not-allowed select-none"
                      title={`${tab.label} — available in later phase`}
                    >
                      <Icon className="h-3.5 w-3.5 shrink-0 opacity-30" />
                      {tab.label}
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      </div>

      {/* Settings footer */}
      <div className="border-t border-border px-3 py-2.5 shrink-0">
        <div className="flex items-center gap-2">
          <Settings className="h-3 w-3 text-muted-foreground/50" />
          <span className="text-[10px] text-muted-foreground/50">ENV</span>
          <span className="ml-auto inline-flex items-center rounded-sm border border-muted-foreground/20 bg-muted px-1.5 py-0.5 text-[10px] font-mono text-muted-foreground">
            WARN
          </span>
        </div>
      </div>
    </nav>
  );
}
