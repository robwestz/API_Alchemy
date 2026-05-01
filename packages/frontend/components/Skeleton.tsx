/**
 * Skeleton — animated placeholder for loading states.
 * Uses Tailwind animate-pulse. Prefer over spinners per design directive.
 *
 * Usage:
 *   <Skeleton className="h-4 w-32" />           // single line
 *   <Skeleton className="h-20 w-full" />         // card block
 *   <SkeletonText lines={3} />                   // paragraph
 */

import { cn } from "@/lib/utils";

interface SkeletonProps {
  className?: string;
}

export function Skeleton({ className }: SkeletonProps) {
  return (
    <div
      className={cn(
        "animate-pulse rounded-md bg-muted",
        className,
      )}
      aria-hidden="true"
    />
  );
}

// ---------------------------------------------------------------------------
// Composite skeletons for common patterns
// ---------------------------------------------------------------------------

/** Multiple stacked skeleton lines — use for text blocks */
export function SkeletonText({ lines = 3 }: { lines?: number }) {
  return (
    <div className="space-y-2" aria-hidden="true">
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton
          key={i}
          className={cn(
            "h-3",
            i === lines - 1 ? "w-3/4" : "w-full",
          )}
        />
      ))}
    </div>
  );
}

/** Project list item skeleton */
export function SkeletonProjectItem() {
  return (
    <div className="flex items-center gap-2 px-2 py-1.5" aria-hidden="true">
      <Skeleton className="h-3 w-3 rounded-sm" />
      <Skeleton className="h-3 flex-1" />
    </div>
  );
}

/** Status card skeleton */
export function SkeletonCard() {
  return (
    <div
      className="rounded-lg border border-border bg-card p-4 space-y-3"
      aria-hidden="true"
    >
      <Skeleton className="h-3 w-24" />
      <Skeleton className="h-7 w-16" />
      <Skeleton className="h-3 w-32" />
    </div>
  );
}

/** Tool button card skeleton */
export function SkeletonToolCard() {
  return (
    <div
      className="rounded-lg border border-border bg-card p-4 space-y-3"
      aria-hidden="true"
    >
      <div className="flex items-center justify-between">
        <Skeleton className="h-3 w-28" />
        <Skeleton className="h-5 w-16 rounded-full" />
      </div>
      <Skeleton className="h-3 w-full" />
      <Skeleton className="h-3 w-4/5" />
      <Skeleton className="h-8 w-24 mt-2" />
    </div>
  );
}
