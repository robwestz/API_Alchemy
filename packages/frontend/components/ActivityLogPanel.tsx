"use client";

/**
 * ActivityLogPanel — collapsible right drawer showing agent activity events.
 *
 * Fas 6a: static placeholder with empty state.
 * Fas 6c: wired to WebSocket topic project:<id> via gateway/main.py websocket_project().
 *
 * Layout position: rightmost column (320px) in 3-column root grid.
 * Collapsed via toggle button in panel header.
 */

import { useState } from "react";
import { ChevronRight, ChevronLeft, Activity } from "lucide-react";
import { cn } from "@/lib/utils";
import type { AgentEvent } from "@/lib/types";

// ---------------------------------------------------------------------------
// Placeholder events for Fas 6a (replaced by WebSocket in 6c)
// ---------------------------------------------------------------------------
const PLACEHOLDER_EVENTS: AgentEvent[] = [];

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function EventBadge({ agentName }: { agentName: string }) {
  const colors: Record<string, string> = {
    Scout: "border-accent/30 bg-accent/10 text-accent",
    Engineer: "border-primary/30 bg-primary/10 text-primary",
    Judge: "border-destructive/30 bg-destructive/10 text-destructive",
    Orchestrator: "border-muted-foreground/30 bg-muted text-muted-foreground",
  };
  const colorClass =
    colors[agentName] ??
    "border-muted-foreground/20 bg-muted text-muted-foreground";

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-sm border px-1.5 py-0.5",
        "text-[10px] font-medium leading-none shrink-0",
        colorClass,
      )}
    >
      {agentName}
    </span>
  );
}

function EventRow({ event }: { event: AgentEvent }) {
  const [expanded, setExpanded] = useState(false);

  const ts = new Date(event.ts);
  const timeStr = ts.toLocaleTimeString("sv-SE", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

  return (
    <div
      className="border-b border-border/50 px-3 py-2 cursor-pointer hover:bg-muted/40 transition-colors"
      onClick={() => setExpanded((v) => !v)}
      title={ts.toISOString()}
    >
      <div className="flex items-start gap-2">
        <code className="font-mono text-[10px] text-muted-foreground/60 shrink-0 mt-0.5 tabular-nums">
          {timeStr}
        </code>
        <div className="flex flex-col gap-1 min-w-0">
          <div className="flex items-center gap-1.5 flex-wrap">
            <EventBadge agentName={event.agent_name} />
            <span className="text-xs text-foreground/80 truncate">
              {event.action}
            </span>
          </div>
          {expanded && event.payload !== null && (
            <pre className="mt-1 text-[10px] font-mono text-muted-foreground bg-muted rounded p-2 overflow-x-auto whitespace-pre-wrap break-all">
              {JSON.stringify(event.payload, null, 2)}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function ActivityLogPanel() {
  const [collapsed, setCollapsed] = useState(false);
  const events = PLACEHOLDER_EVENTS;

  if (collapsed) {
    return (
      <div className="flex flex-col items-center border-l border-border bg-card w-10 shrink-0">
        <button
          className="p-2 mt-3 text-muted-foreground hover:text-foreground transition-colors"
          onClick={() => setCollapsed(false)}
          title="Open Activity Log"
          aria-label="Open Activity Log"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
        <span
          className="mt-4 text-[10px] font-medium text-muted-foreground/50 tracking-widest uppercase"
          style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}
        >
          Activity
        </span>
      </div>
    );
  }

  return (
    <aside className="flex flex-col border-l border-border bg-card w-80 shrink-0 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-3 py-2.5 shrink-0">
        <div className="flex items-center gap-2">
          <Activity className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs font-medium text-foreground">
            Activity Log
          </span>
          {events.length > 0 && (
            <span className="rounded-sm bg-muted px-1.5 py-0.5 text-[10px] font-mono text-muted-foreground">
              {events.length}
            </span>
          )}
        </div>
        <button
          className="text-muted-foreground hover:text-foreground transition-colors p-1 -mr-1"
          onClick={() => setCollapsed(true)}
          title="Collapse Activity Log"
          aria-label="Collapse Activity Log"
        >
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>

      {/* Event list */}
      <div className="flex-1 overflow-y-auto">
        {events.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-2 px-4 py-12 text-center">
            <Activity className="h-6 w-6 text-muted-foreground/30" />
            <p className="text-xs text-muted-foreground/50 leading-relaxed">
              No activity yet.
              <br />
              Run a tool to see logs.
            </p>
            <p className="text-[10px] text-muted-foreground/30 font-mono mt-1">
              WebSocket: Fas 6c
            </p>
          </div>
        ) : (
          <div>
            {events.map((event) => (
              <EventRow key={event.id} event={event} />
            ))}
          </div>
        )}
      </div>
    </aside>
  );
}
