# ApexFlow UI

React frontend for the ApexFlow Agentic AI system.

## Tech Stack

- **Framework**: React 19 + Vite + TypeScript
- **UI**: shadcn/ui + Tailwind CSS
- **State**: TanStack Query (server) + Zustand (client)
- **Graph**: ReactFlow
- **Hosting**: Firebase Hosting (project: `apexflow-ai`, site: `apexflow-console`)

## Development

```bash
# Install dependencies
npm install

# Start dev server (Vite proxy forwards /api/* to localhost:8000)
npm run dev

# Run tests
npm run test

# Build for production
npm run build

# Preview production build locally
npm run preview
```

### Running with the backend

1. Start backend: `AUTH_DISABLED=1 uvicorn api:app --reload` (port 8000)
2. Start frontend: `cd frontend && npm run dev` (port 5173)
3. Open `http://localhost:5173`

Vite's dev server proxies `/api/*`, `/liveness`, and `/readiness` to the backend. The proxy target defaults to `http://localhost:8000` but can be overridden:

```bash
VITE_BACKEND_URL=https://apexflow-api-j56xbd7o2a-uc.a.run.app npm run dev
```

## Firebase Hosting

The frontend is deployed to Firebase Hosting in the `apexflow-ai` GCP project — the same project as the Cloud Run backend. This enables Firebase Hosting rewrites to proxy API calls directly to Cloud Run (same-origin, no CORS needed).

| Setting | Value |
|---|---|
| Project | `apexflow-ai` |
| Site | `apexflow-console` |
| URL | https://apexflow-console.web.app |
| Deploy target | `console` |
| Public dir | `frontend/dist` |

### Rewrites

| Pattern | Target |
|---|---|
| `/api/**` | Cloud Run `apexflow-api` (us-central1) |
| `/liveness` | Cloud Run `apexflow-api` |
| `/readiness` | Cloud Run `apexflow-api` |
| `**` | `/index.html` (SPA catch-all) |

### Deploy

```bash
# From repo root
cd frontend && npm run build && cd ..
firebase deploy --only hosting:console
```

### Cache policy

- `/assets/**` — 1 year, immutable (Vite content-hashed filenames)
- `*.html` — no-cache (always fresh)

## Project Structure

```text
src/
├── components/
│   ├── ui/           # shadcn/ui components
│   ├── layout/       # AppShell, Sidebar
│   ├── runs/         # RunCreator, RunList
│   ├── graph/        # GraphView, AgentNode, NodeDetailPanel
│   └── documents/    # DocumentTree, DocumentChat, ChatMessage
├── contexts/         # SSEContext (shared EventSource connection)
├── hooks/            # useApiHealth, useDbHealth, useSSE (deprecated)
├── services/         # API services (runs, rag, settings)
├── store/            # Zustand stores (useAppStore, useGraphStore)
├── types/            # TypeScript types
├── pages/            # Route pages (Dashboard, Documents, Settings)
├── utils/            # Utilities (cn, formatDate, formatDuration)
└── test/             # Test setup and utilities
```

## API Integration

All API calls go through `fetchAPI()` in `services/api.ts`, which:
- Prepends `VITE_API_URL` (empty string by default — uses relative URLs)
- Attaches `Authorization: Bearer <token>` when an auth token provider is set via `setAuthTokenProvider()`
- Returns parsed JSON with typed generics

`getAPIUrl()` is used for non-fetch requests (health checks, EventSource).

## Known Limitations (Stubbed Endpoints)

- Document chat (streaming `/rag/ask` endpoint not in v2)
- Filesystem operations (createFolder, createFile, saveFile, rename, upload, delete by path)
- Keyword search, ripgrep search, document chunks view, indexing status
- Agent test/save
- Cron job update (PUT)
