import { createContext, useContext, useMemo, type ReactNode } from "react"
import { useQuery } from "@tanstack/react-query"
import { useAppStore } from "@/store"
import { runsService } from "@/services"
import { useAuth } from "@/contexts/AuthContext"

interface ExecutionMetrics {
  currentRunCost: number
  currentRunTokens: number
  isRunning: boolean
  runId: string | null
}

const ExecutionMetricsContext = createContext<ExecutionMetrics | null>(null)

export function ExecutionMetricsProvider({ children }: { children: ReactNode }) {
  const selectedRunId = useAppStore((s) => s.selectedRunId)
  const auth = useAuth()
  const canQueryRun = (!auth.isConfigured || auth.isAuthenticated) && !!selectedRunId

  const { data: runDetail } = useQuery({
    queryKey: ["run", selectedRunId],
    queryFn: () => runsService.get(selectedRunId!),
    enabled: canQueryRun,
    refetchInterval: (query) =>
      query.state.data?.status === "running" ? 2000 : false,
  })

  const metrics = useMemo<ExecutionMetrics>(() => {
    if (!runDetail?.graph?.nodes) {
      return {
        currentRunCost: 0,
        currentRunTokens: 0,
        isRunning: false,
        runId: selectedRunId,
      }
    }

    const nodes = runDetail.graph.nodes
    const totalCost = nodes.reduce((sum, node) => sum + (node.data?.cost || 0), 0)
    const isRunning = runDetail.status === "running"

    return {
      currentRunCost: totalCost,
      currentRunTokens: 0, // Backend doesn't expose token counts yet
      isRunning,
      runId: selectedRunId,
    }
  }, [runDetail, selectedRunId])

  return (
    <ExecutionMetricsContext.Provider value={metrics}>
      {children}
    </ExecutionMetricsContext.Provider>
  )
}

export function useExecutionMetrics() {
  const context = useContext(ExecutionMetricsContext)
  if (!context) {
    throw new Error("useExecutionMetrics must be used within an ExecutionMetricsProvider")
  }
  return context
}
