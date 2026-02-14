import { CheckCircle2, XCircle, Loader2, Wrench } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/utils/utils"
import type { ReasoningEvent, GraphNode } from "@/types"

export interface ConsolidatedStep {
  step_id: string
  status: "in_progress" | "completed" | "failed"
  agent_type?: string
  execution_time?: number
  cost?: number
  error?: string
  tool_calls: Array<{ tool_name: string; args_summary?: string }>
}

/** Normalize metadata that may arrive as a JSON string from JSONB columns. */
export function parseMetadata(metadata: unknown): Record<string, unknown> | null {
  if (metadata == null) return null
  if (typeof metadata === "object" && !Array.isArray(metadata)) return metadata as Record<string, unknown>
  if (typeof metadata === "string") {
    try {
      const parsed = JSON.parse(metadata)
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) return parsed
    } catch { /* not valid JSON */ }
  }
  return null
}

const SENSITIVE_KEYS = new Set([
  "password", "secret", "token", "key", "api_key", "apikey",
  "authorization", "credential", "credentials",
])

/** Mask sensitive values in tool arguments, mirroring backend _mask_sensitive. */
function maskSensitive(obj: unknown): unknown {
  if (obj == null || typeof obj !== "object") return obj
  if (Array.isArray(obj)) return obj.map(maskSensitive)
  const result: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
    result[k] = SENSITIVE_KEYS.has(k.toLowerCase()) ? "***" : maskSensitive(v)
  }
  return result
}

/** Summarize tool arguments as a truncated string. */
function summarizeArgs(args: Record<string, unknown>): string {
  const masked = maskSensitive(args) as Record<string, unknown>
  const text = JSON.stringify(masked)
  return text.length > 200 ? text.slice(0, 200) + "..." : text
}

/** Reconstruct ConsolidatedStep[] from persisted graph nodes. */
export function stepsFromGraphNodes(nodes: GraphNode[]): ConsolidatedStep[] {
  return nodes
    .filter((n) => {
      // Skip synthetic ROOT node and nodes that never executed
      if (n.id === "ROOT") return false
      const s = n.data.status
      return s !== "pending" && s !== "idle" && s !== "stale"
    })
    .map((n) => {
      const d = n.data
      const status: ConsolidatedStep["status"] =
        d.status === "running" ? "in_progress"
        : d.status === "completed" ? "completed"
        : "failed"

      // Extract tool calls from iterations (primary) or calls (fallback)
      const toolCalls: ConsolidatedStep["tool_calls"] = []
      if (d.iterations?.length) {
        for (const iter of d.iterations) {
          const callTool = iter.output?.call_tool as
            | { name?: string; arguments?: Record<string, unknown> }
            | undefined
          if (callTool?.name) {
            toolCalls.push({
              tool_name: callTool.name,
              args_summary: callTool.arguments
                ? summarizeArgs(callTool.arguments)
                : undefined,
            })
          }
        }
      } else if (d.calls?.length) {
        for (const c of d.calls) {
          toolCalls.push({
            tool_name: c.name,
            args_summary: c.arguments ? summarizeArgs(c.arguments) : undefined,
          })
        }
      }

      return {
        step_id: d.label || n.id,
        status,
        agent_type: d.type,
        execution_time: d.execution_time || undefined,
        cost: d.cost || undefined,
        error: d.error || undefined,
        tool_calls: toolCalls,
      }
    })
}

/** Consolidate raw SSE reasoning events into one entry per step. */
export function consolidateEvents(events: ReasoningEvent[]): ConsolidatedStep[] {
  const stepMap = new Map<string, ConsolidatedStep>()
  const stepOrder: string[] = []

  for (const evt of events) {
    const id = evt.step_id
    if (!id) continue

    if (!stepMap.has(id)) {
      stepMap.set(id, {
        step_id: id,
        status: "in_progress",
        agent_type: evt.agent_type,
        tool_calls: [],
      })
      stepOrder.push(id)
    }

    const step = stepMap.get(id)!

    switch (evt.type) {
      case "step_start":
        step.agent_type = step.agent_type || evt.agent_type
        break
      case "tool_call":
        if (evt.tool_name) {
          step.tool_calls.push({
            tool_name: evt.tool_name,
            args_summary: evt.args_summary,
          })
        }
        break
      case "step_complete":
        step.status = "completed"
        step.agent_type = evt.agent_type || step.agent_type
        step.execution_time = evt.execution_time
        step.cost = evt.cost
        break
      case "step_failed":
        step.status = "failed"
        step.agent_type = evt.agent_type || step.agent_type
        step.error = evt.error
        break
    }
  }

  return stepOrder.map((id) => stepMap.get(id)!)
}

export function StepTimelineItem({ step }: { step: ConsolidatedStep }) {
  const { step_id, status, agent_type, execution_time, error, tool_calls } = step

  return (
    <div>
      {/* Main step row */}
      <div className="relative flex items-start gap-3 pl-1">
        <div
          className={cn(
            "relative z-10 mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-background border",
            status === "in_progress" && "border-foreground/30",
            status === "completed" && "border-success/40",
            status === "failed" && "border-destructive/40"
          )}
        >
          {status === "in_progress" && (
            <Loader2 className="h-3 w-3 text-foreground animate-spin" />
          )}
          {status === "completed" && (
            <CheckCircle2 className="h-3 w-3 text-success" />
          )}
          {status === "failed" && (
            <XCircle className="h-3 w-3 text-destructive" />
          )}
        </div>
        <div className="min-w-0 pt-px">
          <p className="text-sm font-medium text-foreground">
            {step_id}
            {execution_time != null && execution_time > 0 && (
              <span className="ml-2 text-xs font-normal text-muted-foreground">
                {execution_time.toFixed(1)}s
              </span>
            )}
          </p>
          {agent_type && (
            <Badge variant="muted" className="mt-1">{agent_type}</Badge>
          )}
          {error && (
            <p className="text-xs text-destructive mt-0.5 line-clamp-3">{error}</p>
          )}
        </div>
      </div>

      {/* Nested tool calls */}
      {tool_calls.map((tc, i) => (
        <div key={i} className="relative flex items-start gap-3 pl-1 ml-4 mt-1.5">
          <div className="relative z-10 mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded bg-muted">
            <Wrench className="h-2.5 w-2.5 text-muted-foreground" />
          </div>
          <div className="min-w-0 pt-px">
            <p className="text-xs text-foreground">
              <span className="font-medium">{tc.tool_name}</span>
            </p>
            {tc.args_summary && (
              <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2 font-mono">
                {tc.args_summary}
              </p>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}
