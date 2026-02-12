import { memo } from "react"
import { Handle, Position } from "@xyflow/react"
import {
  Bot,
  Brain,
  Code,
  Search,
  FileText,
  Loader2,
  CheckCircle2,
  XCircle,
  Circle,
  AlertCircle,
} from "lucide-react"
import { cn } from "@/utils/utils"
import type { NodeData } from "@/types"

const agentIcons: Record<string, React.ElementType> = {
  PlannerAgent: Brain,
  CoderAgent: Code,
  BrowserAgent: Search,
  RetrieverAgent: Search,
  SummarizerAgent: FileText,
  ThinkerAgent: Brain,
  FormatterAgent: FileText,
}

const agentAccentColors: Record<string, { iconBg: string; iconText: string }> = {
  PlannerAgent:    { iconBg: "bg-indigo-500/10 border-indigo-500/20",  iconText: "text-indigo-600 dark:text-indigo-400" },
  CoderAgent:      { iconBg: "bg-emerald-500/10 border-emerald-500/20", iconText: "text-emerald-600 dark:text-emerald-400" },
  BrowserAgent:    { iconBg: "bg-cyan-500/10 border-cyan-500/20",     iconText: "text-cyan-600 dark:text-cyan-400" },
  RetrieverAgent:  { iconBg: "bg-blue-500/10 border-blue-500/20",     iconText: "text-blue-600 dark:text-blue-400" },
  SummarizerAgent: { iconBg: "bg-amber-500/10 border-amber-500/20",   iconText: "text-amber-600 dark:text-amber-400" },
  ThinkerAgent:    { iconBg: "bg-purple-500/10 border-purple-500/20",  iconText: "text-purple-600 dark:text-purple-400" },
  FormatterAgent:  { iconBg: "bg-orange-500/10 border-orange-500/20",  iconText: "text-orange-600 dark:text-orange-400" },
}

const defaultAccent = { iconBg: "bg-muted/40 border-white/10", iconText: "text-foreground/70" }

// Glass card style shared across all statuses — matches mockup's glass-panel
const GLASS_CARD = "bg-white/70 dark:bg-slate-800/70 backdrop-blur-md border-border/40"

const statusConfig: Record<
  string,
  {
    icon: React.ElementType
    iconClass: string
    animate?: boolean
  }
> = {
  pending: {
    icon: Circle,
    iconClass: "text-muted-foreground",
  },
  idle: {
    icon: Circle,
    iconClass: "text-muted-foreground",
  },
  running: {
    icon: Loader2,
    iconClass: "text-foreground",
    animate: true,
  },
  completed: {
    icon: CheckCircle2,
    iconClass: "text-success",
  },
  failed: {
    icon: XCircle,
    iconClass: "text-destructive",
  },
  stale: {
    icon: AlertCircle,
    iconClass: "text-warning",
  },
}

interface AgentNodeProps {
  data: NodeData
  selected?: boolean
}

function AgentNodeComponent({ data, selected }: AgentNodeProps) {
  const AgentIcon = agentIcons[data.type] || Bot
  const config = statusConfig[data.status] || statusConfig.pending
  const StatusIcon = config.icon
  const accent = agentAccentColors[data.type] || defaultAccent
  const nodeIndex = (data as unknown as Record<string, unknown>)._nodeIndex as number | undefined

  return (
    <div
      className={cn(
        "w-56 rounded-xl border p-4",
        "shadow-[0_4px_20px_-2px_rgba(0,0,0,0.05)] transition-all duration-200",
        "hover:shadow-[0_4px_20px_-2px_rgba(0,0,0,0.1)]",
        "animate-node-entrance",
        GLASS_CARD,
        data.status === "stale" && "node-stale",
        selected && "ring-2 ring-primary/50 ring-offset-2 ring-offset-background"
      )}
      style={nodeIndex != null ? { animationDelay: `${nodeIndex * 80}ms` } : undefined}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!bg-border !border-2 !border-background !w-2.5 !h-2.5 !-top-1.5"
      />

      {/* Header row */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <div className={cn("flex h-7 w-7 items-center justify-center rounded-lg border", accent.iconBg)}>
            <AgentIcon className={cn("h-3.5 w-3.5", accent.iconText)} strokeWidth={1.75} />
          </div>
          <span className="font-semibold text-sm tracking-tight">
            {data.label}
          </span>
        </div>
        <StatusIcon
          className={cn(
            "h-4.5 w-4.5 shrink-0",
            config.iconClass,
            config.animate && "animate-spin"
          )}
          strokeWidth={2}
        />
      </div>

      {/* Description */}
      {data.description && (
        <p className="text-xs text-muted-foreground leading-tight">
          {data.description}
        </p>
      )}

      {/* Execution time */}
      {data.execution_time > 0 && (
        <p className="text-[10px] text-muted-foreground font-mono mt-3">
          {(data.execution_time / 1000).toFixed(2)}s
        </p>
      )}

      <Handle
        type="source"
        position={Position.Bottom}
        className="!bg-border !border-2 !border-background !w-2.5 !h-2.5 !-bottom-1.5"
      />
    </div>
  )
}

export const AgentNode = memo(AgentNodeComponent)
