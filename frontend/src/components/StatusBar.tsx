import { useApiHealth, type ConnectionState } from "@/hooks/useApiHealth"
import { useSSEContext, type SSEConnectionState } from "@/contexts/SSEContext"
import { useExecutionMetrics } from "@/contexts/ExecutionMetricsContext"
import { cn } from "@/utils/utils"

interface ConnectionIndicatorProps {
  label: string
  state: ConnectionState | SSEConnectionState
}

function ConnectionIndicator({ label, state }: ConnectionIndicatorProps) {
  const statusConfig = {
    connected: {
      icon: "bg-success",
      className: "",
    },
    connecting: {
      icon: "bg-warning animate-pulse",
      className: "",
    },
    disconnected: {
      icon: "bg-destructive",
      className: "",
    },
  }

  const config = statusConfig[state]

  return (
    <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
      <span className="text-foreground/70">{label}:</span>
      <span
        className={cn(
          "w-2 h-2 rounded-full",
          config.icon,
          config.className
        )}
      />
    </div>
  )
}

function formatCost(cost: number): string {
  if (cost < 0.01) {
    return cost > 0 ? "<$0.01" : "$0.00"
  }
  return "$" + cost.toFixed(2)
}

export function StatusBar() {
  const apiHealth = useApiHealth()
  const { connectionState: sseState } = useSSEContext()
  const metrics = useExecutionMetrics()

  return (
    <footer className="h-7 flex-shrink-0 border-t border-white/10 backdrop-blur-md bg-background/60">
      <div className="h-full px-3 flex items-center justify-between text-xs">
        <div className="flex items-center gap-4">
          <ConnectionIndicator label="API" state={apiHealth.state} />
          <ConnectionIndicator label="SSE" state={sseState} />
        </div>

        <div className="flex items-center gap-3 text-muted-foreground">
          {metrics.runId ? (
            <>
              <span>
                <span className="text-foreground/70">Run Cost:</span>{" "}
                <span className={cn(
                  "tabular-nums",
                  metrics.isRunning && "text-foreground"
                )}>
                  {formatCost(metrics.currentRunCost)}
                </span>
              </span>
              {metrics.isRunning && (
                <span className="text-warning animate-pulse">Running</span>
              )}
            </>
          ) : (
            <span className="text-muted-foreground/60">No run selected</span>
          )}
        </div>
      </div>
    </footer>
  )
}
