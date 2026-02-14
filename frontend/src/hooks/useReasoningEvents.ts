import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useSSESubscription } from "@/contexts/SSEContext"
import { consolidateEvents, type ConsolidatedStep } from "@/components/chat/reasoning-shared"
import type { SSEEvent, ReasoningEvent } from "@/types"

/**
 * Centralized SSE reasoning hook.
 *
 * Subscribes once to the SSE stream, stores raw events keyed by run_id,
 * and returns pre-consolidated steps for each run.
 */
export function useReasoningEvents(
  activeRunId: string | null,
  sessionId: string | null
): { stepsMap: Map<string, ConsolidatedStep[]> } {
  const [eventsMap, setEventsMap] = useState<Map<string, ReasoningEvent[]>>(new Map())
  const prevRunIdRef = useRef<string | null>(null)

  // Clear all events when the session changes
  useEffect(() => {
    setEventsMap(new Map())
  }, [sessionId])

  // Clear events only when a NEW run starts (not when a run completes → null)
  useEffect(() => {
    if (activeRunId && activeRunId !== prevRunIdRef.current) {
      setEventsMap((prev) => {
        const next = new Map(prev)
        next.delete(activeRunId)
        return next
      })
    }
    prevRunIdRef.current = activeRunId
  }, [activeRunId])

  const handleSSEEvent = useCallback(
    (event: SSEEvent) => {
      if (!activeRunId) return

      const { type, data } = event
      if (!["step_start", "step_complete", "step_failed", "tool_call"].includes(type)) return

      const eventSessionId = data.session_id as string | undefined
      if (!eventSessionId || eventSessionId !== activeRunId) return

      const reasoningEvent: ReasoningEvent = {
        type: type as ReasoningEvent["type"],
        step_id: (data.step_id as string) || "",
        session_id: eventSessionId,
        agent_type: data.agent_type as string | undefined,
        tool_name: data.tool_name as string | undefined,
        args_summary: data.args_summary as string | undefined,
        execution_time: data.execution_time as number | undefined,
        cost: data.cost as number | undefined,
        error: data.error as string | undefined,
        timestamp: event.timestamp || new Date().toISOString(),
      }

      setEventsMap((prev) => {
        const next = new Map(prev)
        const existing = next.get(activeRunId) || []
        next.set(activeRunId, [...existing, reasoningEvent])
        return next
      })
    },
    [activeRunId]
  )

  useSSESubscription(handleSSEEvent)

  const stepsMap = useMemo(() => {
    const result = new Map<string, ConsolidatedStep[]>()
    for (const [runId, events] of eventsMap) {
      result.set(runId, consolidateEvents(events))
    }
    return result
  }, [eventsMap])

  return { stepsMap }
}
