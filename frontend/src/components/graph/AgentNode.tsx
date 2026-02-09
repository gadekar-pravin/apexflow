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

const agentAccentColors: Record<string, { border: string; iconBg: string }> = {
  PlannerAgent:    { border: "border-l-indigo-500",  iconBg: "bg-indigo-500/10 border-indigo-500/20" },
  CoderAgent:      { border: "border-l-emerald-500", iconBg: "bg-emerald-500/10 border-emerald-500/20" },
  BrowserAgent:    { border: "border-l-cyan-500",    iconBg: "bg-cyan-500/10 border-cyan-500/20" },
  RetrieverAgent:  { border: "border-l-violet-500",  iconBg: "bg-violet-500/10 border-violet-500/20" },
  SummarizerAgent: { border: "border-l-amber-500",   iconBg: "bg-amber-500/10 border-amber-500/20" },
  ThinkerAgent:    { border: "border-l-purple-500",  iconBg: "bg-purple-500/10 border-purple-500/20" },
  FormatterAgent:  { border: "border-l-orange-500",  iconBg: "bg-orange-500/10 border-orange-500/20" },
}

const defaultAccent = { border: "", iconBg: "bg-muted/40 border-white/10" }

const statusConfig: Record<
  string,
  {
    icon: React.ElementType
    containerClass: string
    iconClass: string
    animate?: boolean
    glow?: boolean
    glowClass?: string
  }
> = {
  pending: {
    icon: Circle,
    containerClass: "border-border/60 bg-card/70 backdrop-blur-xs",
    iconClass: "text-muted-foreground",
  },
  idle: {
    icon: Circle,
    containerClass: "border-border/60 bg-card/70 backdrop-blur-xs",
    iconClass: "text-muted-foreground",
  },
  running: {
    icon: Loader2,
    containerClass: "border-primary/40 bg-primary/5 backdrop-blur-xs",
    iconClass: "text-primary",
    animate: true,
    glow: true,
  },
  completed: {
    icon: CheckCircle2,
    containerClass: "border-success/30 bg-success/5 backdrop-blur-xs",
    iconClass: "text-success",
    glowClass: "node-success-glow",
  },
  failed: {
    icon: XCircle,
    containerClass: "border-destructive/30 bg-destructive/5 backdrop-blur-xs",
    iconClass: "text-destructive",
    glowClass: "node-error-glow",
  },
  stale: {
    icon: AlertCircle,
    containerClass: "border-warning/30 bg-warning/5 backdrop-blur-xs",
    iconClass: "text-warning",
    glowClass: "node-warning-glow",
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
        "rounded-md border border-l-[3px] px-3.5 py-2.5 min-w-[160px] max-w-[200px]",
        "shadow-glass-sm transition-all duration-200",
        "hover:scale-[1.02] hover:shadow-glass-md",
        "animate-node-entrance",
        accent.border,
        config.containerClass,
        config.glow && "node-active-glow",
        config.glowClass,
        data.status === "stale" && "node-stale",
        selected && "ring-1 ring-primary/60 ring-offset-1 ring-offset-background shadow-glass-glow"
      )}
      style={nodeIndex != null ? { animationDelay: `${nodeIndex * 80}ms` } : undefined}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!bg-border !border-2 !border-background !w-2.5 !h-2.5 !-top-1.5"
      />

      {/* Header row */}
      <div className="flex items-center gap-2">
        <div className={cn("flex h-6 w-6 items-center justify-center rounded backdrop-blur-xs border", accent.iconBg)}>
          <AgentIcon className="h-3.5 w-3.5 text-foreground/70" strokeWidth={1.75} />
        </div>
        <span className="font-medium text-sm tracking-tight truncate flex-1">
          {data.label}
        </span>
        <StatusIcon
          className={cn(
            "h-3.5 w-3.5 shrink-0",
            config.iconClass,
            config.animate && "animate-spin"
          )}
          strokeWidth={2}
        />
      </div>

      {/* Description */}
      {data.description && (
        <p className="text-xs text-muted-foreground mt-1.5 line-clamp-2 leading-relaxed">
          {data.description}
        </p>
      )}

      {/* Execution time */}
      {data.execution_time > 0 && (
        <div className="flex items-center gap-1 mt-2 pt-2 border-t border-border/40">
          <span className="text-2xs text-muted-foreground font-mono">
            {(data.execution_time / 1000).toFixed(2)}s
          </span>
        </div>
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
