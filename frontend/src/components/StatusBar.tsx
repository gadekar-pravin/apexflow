import { useApiHealth, type ConnectionState } from "@/hooks/useApiHealth"
import { useDbHealth } from "@/hooks/useDbHealth"
import { useSSEContext, type SSEConnectionState } from "@/contexts/SSEContext"
import { useExecutionMetrics } from "@/contexts/ExecutionMetricsContext"
import { useAuth } from "@/contexts/AuthContext"
import { Button } from "@/components/ui/button"
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
  if (cost === 0) return "$0.00"
  if (cost < 0.01) return "$" + cost.toFixed(6)
  return "$" + cost.toFixed(2)
}

export function StatusBar() {
  const apiHealth = useApiHealth()
  const dbHealth = useDbHealth()
  const { connectionState: sseState } = useSSEContext()
  const metrics = useExecutionMetrics()
  const auth = useAuth()
  const authState: ConnectionState = auth.isInitializing
    ? "connecting"
    : auth.isAuthenticated
      ? "connected"
      : "disconnected"

  return (
    <footer className="h-7 flex-shrink-0 border-t border-white/10 backdrop-blur-md bg-background/60">
      <div className="h-full px-3 flex items-center justify-between text-xs">
        <div className="flex items-center gap-4">
          <ConnectionIndicator label="API" state={apiHealth.state} />
          <ConnectionIndicator label="DB" state={dbHealth} />
          <ConnectionIndicator label="SSE" state={sseState} />
          <ConnectionIndicator label="Auth" state={authState} />
          {auth.isConfigured && auth.isAuthenticated && (
            <span className="text-muted-foreground/80 truncate max-w-40">
              {auth.user?.email || "Signed in"}
            </span>
          )}
        </div>

        <div className="flex items-center gap-3 text-muted-foreground">
          {auth.isConfigured && auth.isAuthenticated && (
            <Button
              variant="ghost"
              size="sm"
              className="h-6 px-2 text-xs"
              onClick={() => void auth.signOut()}
            >
              Sign out
            </Button>
          )}
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
          {auth.lastError && (
            <span className="text-destructive/80 truncate max-w-64">{auth.lastError}</span>
          )}
        </div>
      </div>
    </footer>
  )
}
