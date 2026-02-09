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

const USD_TO_INR = 95

function formatCost(cost: number): { usd: string; inr: string } {
  const inr = cost * USD_TO_INR
  if (cost === 0) return { usd: "$0.00", inr: "₹0.00" }
  if (cost < 0.01) return { usd: "$" + cost.toFixed(6), inr: "₹" + inr.toFixed(4) }
  return { usd: "$" + cost.toFixed(2), inr: "₹" + inr.toFixed(2) }
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
              variant="outline"
              size="sm"
              className="h-6 px-2 text-xs text-red-400 border-red-400/40 hover:bg-red-400/10 hover:text-red-300"
              onClick={() => void auth.signOut()}
            >
              Sign out
            </Button>
          )}
          {metrics.runId ? (
            <>
              <span className="flex items-center gap-1.5">
                <span className="text-foreground/50">Run Cost:</span>
                <span className="font-mono tabular-nums text-red-400">
                  {formatCost(metrics.currentRunCost).usd}
                </span>
                <span className="font-mono tabular-nums text-cyan-500">
                  {formatCost(metrics.currentRunCost).inr}
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
