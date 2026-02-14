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
  PlannerAgent:    { iconBg: "bg-primary/10 border-primary/20",  iconText: "text-primary" },
  CoderAgent:      { iconBg: "bg-success/10 border-success/20", iconText: "text-success" },
  BrowserAgent:    { iconBg: "bg-primary/10 border-primary/25",  iconText: "text-primary" },
  RetrieverAgent:  { iconBg: "bg-primary/15 border-primary/30",  iconText: "text-primary" },
  SummarizerAgent: { iconBg: "bg-warning/10 border-warning/20",  iconText: "text-warning" },
  ThinkerAgent:    { iconBg: "bg-primary/15 border-primary/30",  iconText: "text-primary" },
  FormatterAgent:  { iconBg: "bg-primary/20 border-primary/30",  iconText: "text-primary" },
}

const defaultAccent = { iconBg: "bg-muted/40 border-primary/15", iconText: "text-foreground/70" }

// Glass card style shared across all statuses — matches mockup's glass-panel
const GLASS_CARD = "bg-card/80 backdrop-blur-md border-primary/15"

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
    iconClass: "text-primary",
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
            "size-[18px] shrink-0",
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
