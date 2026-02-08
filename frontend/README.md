# ApexFlow UI

React frontend for the ApexFlow Agentic AI system.

## Tech Stack

- **Framework**: React + Vite + TypeScript
- **UI**: shadcn/ui + Tailwind CSS
- **State**: React Query (server) + Zustand (client)
- **Graph**: ReactFlow
- **Hosting**: Firebase Hosting

## Development

```bash
# Install dependencies
npm install

# Start dev server (connects to backend at localhost:8000)
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

## Project Structure

```
src/
├── components/
│   ├── ui/           # shadcn/ui components
│   ├── layout/       # AppShell, Sidebar
│   ├── runs/         # RunCreator, RunList
│   ├── graph/        # GraphView, AgentNode, NodeDetailPanel
│   └── documents/    # DocumentTree, DocumentChat, ChatMessage
├── hooks/            # useSSE
├── services/         # API services (runs, rag, settings)
├── store/            # Zustand stores
├── types/            # TypeScript types
├── pages/            # Route pages
└── lib/              # Utilities
```

## Environment Variables

```env
# .env.local (development)
VITE_API_URL=http://localhost:8000

# .env.production (Firebase)
VITE_API_URL=https://your-cloud-run-url.run.app
```

## Firebase Deployment

```bash
# Login to Firebase
firebase login

# Deploy to Firebase Hosting
npm run build
firebase deploy --only hosting
```

## Features

- **Dashboard**: Create and monitor agent runs with real-time graph visualization
- **Documents**: Browse and chat with indexed documents (RAG)
- **Settings**: Configure agent and system settings
