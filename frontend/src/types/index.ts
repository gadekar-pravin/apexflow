export * from "./run"
export * from "./document"
export * from "./settings"
export * from "./chat"

// SSE Event types matching backend routers/stream.py
export interface SSEEvent {
  type: string
  data: Record<string, unknown>
  timestamp?: string
}

// MCP types
export interface MCPTool {
  name: string
  description: string
  server: string
  inputSchema?: Record<string, unknown>
}

// Notification types
export interface Notification {
  id: string
  title: string
  message: string
  type: "info" | "success" | "warning" | "error"
  read: boolean
  created_at: string
}

// Cron job types (v2: schedule→cron, added agent_type, removed enabled/last_run/next_run)
export interface CronJob {
  id: string
  name: string
  cron: string
  agent_type: string
  query: string
}
