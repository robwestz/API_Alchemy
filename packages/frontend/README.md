# API Alchemy Engine — Frontend

Next.js 15 App Router frontend for the Lab UI (Fas 6).

## Stack

- Next.js 15 (App Router, React Server Components)
- React 19
- Tailwind CSS 4
- shadcn/ui pattern (Radix primitives + cva)
- TypeScript strict
- Geist Sans + Geist Mono fonts

## Running locally

```bash
cd packages/frontend
npm install
npm run dev   # http://localhost:3000
```

The backend gateway must be running separately:

```bash
# From repo root
uvicorn packages.gateway.main:app --host 127.0.0.1 --port 8000 --reload
```

## Configuration

Copy `.env.example` to `.env.local` and adjust if needed:

```bash
cp .env.example .env.local
```

| Variable | Default | Description |
|---|---|---|
| `NEXT_PUBLIC_API_BASE` | `http://localhost:8000` | Gateway base URL |

The frontend degrades gracefully when the backend is offline — status cards show "Offline" and tool/project lists show empty states.

## Other commands

```bash
npm run build       # production build
npm run type-check  # tsc --noEmit (type errors only)
npm run lint        # eslint
```

## Structure

```
app/
  layout.tsx               # Root layout: 3-column grid (Sidebar + main + ActivityLog)
  page.tsx                 # Dashboard (/)
  globals.css              # Design tokens (CSS variables), Tailwind imports
  source/
    page.tsx               # Source tab (/source)
    SourceIngestForm.tsx   # Client island: URL ingest form
components/
  Sidebar.tsx              # Left nav (240px): projects, navigation, settings
  ActivityLogPanel.tsx     # Right drawer (320px): agent event log
  ToolButton.tsx           # ToolSpec card with execute button
  Skeleton.tsx             # Animated loading placeholders
  ui/
    button.tsx             # shadcn Button (cva variants)
lib/
  api-client.ts            # Type-safe fetch wrapper for gateway endpoints
  types.ts                 # TypeScript types mirroring Python Pydantic models
  utils.ts                 # cn() utility (clsx + tailwind-merge)
```

## Fas 6 scope

| Sub-phase | Status | Notes |
|---|---|---|
| 6a Foundation | Done | Layout, types, api-client, Source tab shell |
| 6b Tool wiring | Pending | executeTool() calls, form submissions |
| 6c WebSocket | Pending | ActivityLog live via ws://localhost:8000/ws/projects/:id |
| 6d Light mode | Pending | CSS variable toggle, no design changes |
