import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * cn() — shadcn/ui pattern: merge Tailwind classes with conflict resolution.
 * Combines clsx (conditional classes) + tailwind-merge (dedup conflicting utilities).
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
