import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { CheckCircle2, XCircle, Loader2, Wrench, Search, FileText, Sparkles } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { useSSESubscription } from "@/contexts/SSEContext"
import { cn } from "@/utils/utils"
import type { SSEEvent, ReasoningEvent } from "@/types"

interface ConsolidatedStep {
  step_id: string
  status: "in_progress" | "completed" | "failed"
  agent_type?: string
  execution_time?: number
  cost?: number
  error?: string
  tool_calls: Array<{ tool_name: string; args_summary?: string }>
}

interface ReasoningSidebarProps {
  activeRunId: string | null
  sessionId: string | null
}

export function ReasoningSidebar({ activeRunId, sessionId }: ReasoningSidebarProps) {
  const [events, setEvents] = useState<ReasoningEvent[]>([])
  const prevRunIdRef = useRef<string | null>(null)

  // Clear events when session changes (user switched or created new chat)
  useEffect(() => {
    setEvents([])
  }, [sessionId])

  // Clear events only when a NEW run starts, not when a run completes (null)
  useEffect(() => {
    if (activeRunId && activeRunId !== prevRunIdRef.current) {
      setEvents([])
    }
    prevRunIdRef.current = activeRunId
  }, [activeRunId])

  const handleSSEEvent = useCallback(
    (event: SSEEvent) => {
      if (!activeRunId) return

      const { type, data } = event
      if (!["step_start", "step_complete", "step_failed", "tool_call"].includes(type)) return

      // Filter by session_id — require match, reject events without session_id
      const sessionId = data.session_id as string | undefined
      if (!sessionId || sessionId !== activeRunId) return

      const reasoningEvent: ReasoningEvent = {
        type: type as ReasoningEvent["type"],
        step_id: (data.step_id as string) || "",
        session_id: sessionId || "",
        agent_type: data.agent_type as string | undefined,
        tool_name: data.tool_name as string | undefined,
        args_summary: data.args_summary as string | undefined,
        execution_time: data.execution_time as number | undefined,
        cost: data.cost as number | undefined,
        error: data.error as string | undefined,
        timestamp: event.timestamp || new Date().toISOString(),
      }

      setEvents((prev) => [...prev, reasoningEvent])
    },
    [activeRunId]
  )

  useSSESubscription(handleSSEEvent)

  // Consolidate raw events by step_id into one entry per step
  const consolidatedSteps = useMemo(() => {
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
  }, [events])

  if (!activeRunId && events.length === 0) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <div className="space-y-5">
          <div className="text-center space-y-1.5">
            <h3 className="text-sm font-semibold text-foreground">
              Step-by-step analysis
            </h3>
            <p className="text-xs text-muted-foreground">
              Watch the AI work in real-time:
            </p>
          </div>

          <div className="space-y-3">
            {[
              { icon: Search, label: "Search your documents" },
              { icon: FileText, label: "Analyze and extract insights" },
              { icon: Sparkles, label: "Generate a response" },
            ].map((item) => (
              <div key={item.label} className="flex items-center gap-2.5">
                <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-primary/30">
                  <item.icon className="h-3 w-3 text-primary/60" />
                </div>
                <span className="text-xs text-muted-foreground">{item.label}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    )
  }

  return (
    <ScrollArea className="h-full">
      <div className="p-4 space-y-1">
        <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-3">
          Reasoning
        </h3>

        <div className="relative">
          {/* Timeline line */}
          {consolidatedSteps.length > 0 && (
            <div className="absolute left-3 top-3 bottom-3 w-px bg-border" />
          )}

          <div className="space-y-3">
            {consolidatedSteps.map((step) => (
              <StepTimelineItem key={step.step_id} step={step} />
            ))}
          </div>
        </div>
      </div>
    </ScrollArea>
  )
}

function StepTimelineItem({ step }: { step: ConsolidatedStep }) {
  const { step_id, status, agent_type, execution_time, error, tool_calls } = step

  return (
    <div>
      {/* Main step row */}
      <div className="relative flex items-start gap-3 pl-1">
        <div
          className={cn(
            "relative z-10 mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-background border",
            status === "in_progress" && "border-primary/40",
            status === "completed" && "border-success/40",
            status === "failed" && "border-destructive/40"
          )}
        >
          {status === "in_progress" && (
            <Loader2 className="h-3 w-3 text-primary animate-spin" />
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
