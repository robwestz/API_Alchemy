"use client";

/**
 * ToolButton — renders a ToolSpec as an interactive card.
 *
 * Displays: tool name (monospace), description, agent_allowed badge.
 * Execute button: placeholder dialog in Fas 6a, wired to api-client in 6b.
 * Hover: border-primary highlight per design directive.
 *
 * Props:
 *   tool: ToolSpec — from GET /api/tools, filtered by agent_allowed && ui_visible
 */

import { useState } from "react";
import { Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ToolSpec } from "@/lib/types";

interface ToolButtonProps {
  tool: ToolSpec;
  onExecute?: (tool: ToolSpec) => void;
}

export function ToolButton({ tool, onExecute }: ToolButtonProps) {
  const [hovered, setHovered] = useState(false);

  return (
    <div
      className={cn(
        "group relative rounded-lg border bg-card p-4 transition-all duration-150",
        "flex flex-col gap-3",
        hovered
          ? "border-primary/60 shadow-[0_0_0_1px_hsl(var(--primary)/0.2)]"
          : "border-border hover:border-primary/40",
      )}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {/* Header row: name + badge */}
      <div className="flex items-start justify-between gap-2">
        <code className="font-mono text-xs text-foreground/90 leading-relaxed break-all">
          {tool.name}
        </code>
        <div className="flex items-center gap-1.5 shrink-0">
          {tool.agent_allowed && (
            <span className="inline-flex items-center rounded-sm border border-accent/30 bg-accent/10 px-1.5 py-0.5 text-[10px] font-medium text-accent leading-none">
              agent
            </span>
          )}
          {tool.ui_component && (
            <span className="inline-flex items-center rounded-sm border border-muted-foreground/20 bg-muted px-1.5 py-0.5 text-[10px] font-mono text-muted-foreground leading-none">
              {tool.ui_component}
            </span>
          )}
        </div>
      </div>

      {/* Description */}
      <p className="text-xs text-muted-foreground leading-relaxed line-clamp-3">
        {tool.description}
      </p>

      {/* Schema hints — shown on hover */}
      {hovered && (
        <div className="flex gap-3 text-[10px] font-mono text-muted-foreground/60">
          <span>
            in:{" "}
            {Object.keys(
              (tool.input_schema as { properties?: Record<string, unknown> })
                .properties ?? {},
            ).length}{" "}
            fields
          </span>
          <span>
            out:{" "}
            {Object.keys(
              (tool.output_schema as { properties?: Record<string, unknown> })
                .properties ?? {},
            ).length}{" "}
            fields
          </span>
        </div>
      )}

      {/* Execute button */}
      <div className="mt-auto pt-1">
        <Button
          size="sm"
          variant="outline"
          className="gap-1.5 text-xs"
          onClick={() => onExecute?.(tool)}
          title={`Execute ${tool.name}`}
        >
          <Zap className="h-3 w-3" />
          Execute
        </Button>
      </div>
    </div>
  );
}
