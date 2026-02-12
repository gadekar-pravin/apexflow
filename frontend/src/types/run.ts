// Run types matching backend routers/runs.py

export interface RunRequest {
  query: string
  agent_type?: string
}

export interface RunResponse {
  id: string
  status: "starting" | "running" | "completed" | "failed" | "stopping"
  created_at: string
  query: string
}

export interface RunSummary {
  id: string
  query: string
  created_at: string
  status: "running" | "completed" | "failed" | "pending"
  total_tokens?: number
}

export interface RunDetail {
  id: string
  status: string
  graph: {
    nodes: GraphNode[]
    edges: GraphEdge[]
  } | null
}

export interface GraphNode {
  id: string
  type: "agentNode"
  position: { x: number; y: number }
  data: NodeData
}

export interface NodeData {
  label: string
  type: string
  status: "pending" | "running" | "completed" | "failed" | "stale" | "idle"
  description: string
  prompt: string
  reads: string[]
  writes: string[]
  inputs?: Record<string, unknown>
  cost: number
  execution_time: number
  input_tokens?: number
  output_tokens?: number
  total_tokens?: number
  start_time?: string
  end_time?: string
  output: string
  error: string
  execution_result?: ExecutionResult
  iterations?: Iteration[]
  logs?: string[]
  execution_logs?: string
  calls?: ToolCall[]
}

export interface ExecutionResult {
  status: "success" | "error"
  result?: Record<string, unknown>
  error?: string
}

export interface Iteration {
  iteration: number
  output: Record<string, unknown>
  tool_result?: string
  execution_result?: ExecutionResult
}

export interface ToolCall {
  name: string
  arguments: Record<string, unknown>
  result?: string
}

export interface GraphEdge {
  id: string
  source: string
  target: string
  type: "custom"
  animated: boolean
  style: {
    stroke: string
    strokeDasharray: string
  }
}

export interface UserInputRequest {
  node_id: string
  response: string
}
