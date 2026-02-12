export interface AgentChatSession {
  id: string
  user_id: string
  target_type: string
  target_id: string
  title: string
  model: string | null
  created_at: string
  updated_at: string
}

export interface AgentChatMessage {
  id: string
  session_id: string
  role: "user" | "assistant" | "system"
  content: string
  metadata: Record<string, unknown> | null
  created_at: string
}

export interface ReasoningEvent {
  type: "step_start" | "step_complete" | "step_failed" | "tool_call"
  step_id: string
  session_id: string
  agent_type?: string
  tool_name?: string
  args_summary?: string
  execution_time?: number
  cost?: number
  error?: string
  timestamp: string
}
