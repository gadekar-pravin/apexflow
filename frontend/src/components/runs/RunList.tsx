import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  CheckCircle2,
  XCircle,
  Loader2,
  Trash2,
  Circle,
} from "lucide-react"
import { cn } from "@/utils/utils"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Badge } from "@/components/ui/badge"
import { runsService } from "@/services"
import { isUnauthorizedError, isForbiddenError } from "@/services/api"
import { useAuth } from "@/contexts/AuthContext"
import { useAppStore } from "@/store"
import { formatDate } from "@/utils/utils"
import type { RunSummary } from "@/types"

const statusConfig = {
  running: {
    icon: Loader2,
    color: "text-primary",
    badge: "default" as const,
    animate: true,
  },
  completed: {
    icon: CheckCircle2,
    color: "text-success",
    badge: "success" as const,
    animate: false,
  },
  failed: {
    icon: XCircle,
    color: "text-destructive",
    badge: "destructive" as const,
    animate: false,
  },
  pending: {
    icon: Circle,
    color: "text-muted-foreground",
    badge: "muted" as const,
    animate: false,
  },
}

export function RunList() {
  const queryClient = useQueryClient()
  const { selectedRunId, setSelectedRunId } = useAppStore()
  const auth = useAuth()
  const canQueryRuns = !auth.isConfigured || auth.isAuthenticated

  const { data: runs, isLoading, error } = useQuery({
    queryKey: ["runs"],
    queryFn: () => runsService.list(),
    enabled: canQueryRuns,
    refetchInterval: (query) =>
      isUnauthorizedError(query.state.error) || isForbiddenError(query.state.error) ? false : 5000,
  })

  const deleteRun = useMutation({
    mutationFn: (id: string) => runsService.delete(id),
    onSuccess: (_, deletedId) => {
      queryClient.invalidateQueries({ queryKey: ["runs"] })
      if (selectedRunId === deletedId) {
        setSelectedRunId(null)
      }
    },
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-6">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!runs?.length) {
    if (isForbiddenError(error)) {
      return (
        <div className="px-4 py-8 text-center text-sm text-muted-foreground">
          Access denied. Your account is not authorized to use this application.
        </div>
      )
    }

    return (
      <div className="px-4 py-8 text-center text-sm text-muted-foreground">
        No runs yet. Create one above to get started.
      </div>
    )
  }

  return (
    <ScrollArea className="h-[calc(100vh-280px)]">
      <div className="space-y-1 p-2 pt-3">
        {runs.map((run: RunSummary) => {
          const config = statusConfig[run.status] || statusConfig.pending
          const Icon = config.icon
          const isSelected = selectedRunId === run.id

          return (
            <div
              key={run.id}
              className={cn(
                "group flex items-start gap-2.5 rounded-md px-3 py-2.5 cursor-pointer transition-all duration-150",
                isSelected
                  ? "bg-primary/5 backdrop-blur-xs border border-primary/20 shadow-sm shadow-primary/5"
                  : "border border-transparent hover:bg-muted/40 hover:backdrop-blur-xs"
              )}
              onClick={() => setSelectedRunId(run.id)}
            >
              <Icon
                className={cn(
                  "h-4 w-4 mt-0.5 shrink-0",
                  config.color,
                  config.animate && "animate-spin"
                )}
                strokeWidth={2}
              />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate leading-tight">{run.query}</p>
                <div className="flex items-center gap-2 mt-1.5">
                  <Badge variant={config.badge} className="text-2xs capitalize">
                    {run.status}
                  </Badge>
                  <span className="text-2xs text-muted-foreground">
                    {formatDate(run.created_at)}
                  </span>
                </div>
              </div>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 opacity-0 group-hover:opacity-100 transition-opacity -mr-1"
                onClick={(e) => {
                  e.stopPropagation()
                  deleteRun.mutate(run.id)
                }}
              >
                <Trash2 className="h-3 w-3 text-muted-foreground hover:text-destructive" strokeWidth={1.75} />
              </Button>
            </div>
          )
        })}
      </div>
    </ScrollArea>
  )
}
