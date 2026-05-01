"use client";

/**
 * SourceIngestForm — client island for the URL ingest form on /source.
 *
 * Fas 6a: form UI with validation state, submit is placeholder (no backend call).
 * Fas 6b: wires to executeTool("ingest_url", { url }) via api-client.
 *
 * Design: large monospace URL input, full-width, prominent but not gaudy.
 */

import { useState } from "react";
import { ArrowRight, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type FormState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success"; message: string }
  | { status: "error"; message: string };

export function SourceIngestForm() {
  const [url, setUrl] = useState("");
  const [formState, setFormState] = useState<FormState>({ status: "idle" });

  const isLoading = formState.status === "loading";
  const isValidUrl = url.trim().length > 0;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!isValidUrl || isLoading) return;

    setFormState({ status: "loading" });

    // Fas 6a placeholder — wired to executeTool in Fas 6b
    await new Promise((r) => setTimeout(r, 400));
    setFormState({
      status: "error",
      message: 'Ingest not yet wired — executeTool("ingest_url") available in Fas 6b.',
    });
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground/60">
          Ingest
        </h2>
        <span className="text-[10px] font-mono text-muted-foreground/40">
          tool: ingest_url
        </span>
      </div>

      <form onSubmit={handleSubmit} className="space-y-2">
        {/* URL input */}
        <div className="relative">
          <input
            type="url"
            value={url}
            onChange={(e) => {
              setUrl(e.target.value);
              if (formState.status !== "idle") {
                setFormState({ status: "idle" });
              }
            }}
            placeholder="https://api.example.com/data or paste JSON URL..."
            className={cn(
              "w-full rounded-md border bg-muted/50 px-3 py-2.5",
              "font-mono text-sm text-foreground placeholder:text-muted-foreground/40",
              "focus:outline-none focus:ring-1 focus:ring-ring",
              "transition-colors duration-150",
              formState.status === "error"
                ? "border-destructive/50"
                : "border-border focus:border-primary/50",
            )}
            aria-label="Source URL"
            autoComplete="off"
            spellCheck={false}
            disabled={isLoading}
          />
        </div>

        {/* Submit row */}
        <div className="flex items-center gap-3">
          <Button
            type="submit"
            size="sm"
            disabled={!isValidUrl || isLoading}
            className="gap-1.5"
          >
            {isLoading ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <ArrowRight className="h-3 w-3" />
            )}
            {isLoading ? "Ingesting..." : "Ingest"}
          </Button>

          {/* Status feedback */}
          {formState.status === "error" && (
            <span className="text-[11px] text-destructive/80 font-mono">
              {formState.message}
            </span>
          )}
          {formState.status === "success" && (
            <span className="text-[11px] text-primary font-mono">
              {formState.message}
            </span>
          )}
        </div>
      </form>
    </div>
  );
}
