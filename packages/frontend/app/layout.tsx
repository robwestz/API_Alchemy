/**
 * Root layout — API Alchemy Engine Lab UI.
 *
 * 3-column grid:
 *   [Sidebar 240px] [Main content flex-1] [ActivityLog 320px collapsible]
 *
 * Dark mode forced via className="dark" on <html>.
 * Geist Sans (UI) + Geist Mono (code/data) via geist package fonts.
 * globals.css defines CSS custom properties (design tokens).
 */

import type { Metadata } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import { Sidebar } from "@/components/Sidebar";
import { ActivityLogPanel } from "@/components/ActivityLogPanel";
import "./globals.css";

export const metadata: Metadata = {
  title: "API Alchemy Engine",
  description:
    "Autonom motor: idé → dataprodukt via agent-svärm. " +
    "Ingest, schema inference, insights, API spec, product brief.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="sv"
      className={`dark ${GeistSans.variable} ${GeistMono.variable}`}
      suppressHydrationWarning
    >
      <body className="bg-background text-foreground antialiased font-sans">
        {/* 3-column root layout — full viewport height, no scroll on body */}
        <div className="flex h-screen w-screen overflow-hidden">
          {/* Col 1: Sidebar (240px fixed) */}
          <Sidebar />

          {/* Col 2: Main content area (flex-1, independently scrollable) */}
          <main className="flex-1 overflow-y-auto overflow-x-hidden min-w-0">
            {children}
          </main>

          {/* Col 3: Activity Log panel (320px, collapsible to 40px) */}
          <ActivityLogPanel />
        </div>
      </body>
    </html>
  );
}
