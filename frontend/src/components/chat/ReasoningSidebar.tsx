import { useCallback, useEffect, useState } from "react"
import { CheckCircle2, XCircle, Loader2, Wrench, Search, FileText, Sparkles } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { useSSESubscription } from "@/contexts/SSEContext"
import type { SSEEvent, ReasoningEvent } from "@/types"

interface ReasoningSidebarProps {
  activeRunId: string | null
}

export function ReasoningSidebar({ activeRunId }: ReasoningSidebarProps) {
  const [events, setEvents] = useState<ReasoningEvent[]>([])

  // Clear events when run changes (including when set to null)
  useEffect(() => {
    setEvents([])
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
          {events.length > 0 && (
            <div className="absolute left-3 top-3 bottom-3 w-px bg-border" />
          )}

          <div className="space-y-3">
            {events.map((evt, i) => (
              <TimelineItem key={i} event={evt} />
            ))}
          </div>
        </div>
      </div>
    </ScrollArea>
  )
}

function TimelineItem({ event }: { event: ReasoningEvent }) {
  const { type, step_id, agent_type, tool_name, args_summary, execution_time, error } = event

  if (type === "step_start") {
    return (
      <div className="relative flex items-start gap-3 pl-1">
        <div className="relative z-10 mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-background border border-primary/40">
          <Loader2 className="h-3 w-3 text-primary animate-spin" />
        </div>
        <div className="min-w-0 pt-px">
          <p className="text-sm font-medium text-foreground">{step_id}</p>
          {agent_type && (
            <Badge variant="muted" className="mt-1">{agent_type}</Badge>
          )}
        </div>
      </div>
    )
  }

  if (type === "tool_call") {
    return (
      <div className="relative flex items-start gap-3 pl-1 ml-4">
        <div className="relative z-10 mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded bg-muted">
          <Wrench className="h-2.5 w-2.5 text-muted-foreground" />
        </div>
        <div className="min-w-0 pt-px">
          <p className="text-xs text-foreground">
            <span className="font-medium">{tool_name}</span>
          </p>
          {args_summary && (
            <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2 font-mono">
              {args_summary}
            </p>
          )}
        </div>
      </div>
    )
  }

  if (type === "step_complete") {
    return (
      <div className="relative flex items-start gap-3 pl-1">
        <div className="relative z-10 mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-background border border-success/40">
          <CheckCircle2 className="h-3 w-3 text-success" />
        </div>
        <div className="min-w-0 pt-px">
          <p className="text-sm text-foreground">{step_id}</p>
          {execution_time != null && execution_time > 0 && (
            <p className="text-xs text-muted-foreground mt-0.5">
              {execution_time.toFixed(1)}s
            </p>
          )}
        </div>
      </div>
    )
  }

  if (type === "step_failed") {
    return (
      <div className="relative flex items-start gap-3 pl-1">
        <div className="relative z-10 mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-background border border-destructive/40">
          <XCircle className="h-3 w-3 text-destructive" />
        </div>
        <div className="min-w-0 pt-px">
          <p className="text-sm text-foreground">{step_id}</p>
          {error && (
            <p className="text-xs text-destructive mt-0.5 line-clamp-3">{error}</p>
          )}
        </div>
      </div>
    )
  }

  return null
}
