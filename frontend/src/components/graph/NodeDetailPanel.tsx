import { useState, useCallback } from "react"
import { useQuery } from "@tanstack/react-query"
import {
  X,
  Clock,
  DollarSign,
  ArrowRight,
  ArrowLeft,
  CheckCircle2,
  XCircle,
  Loader2,
  AlertCircle,
  Circle,
  Copy,
  Check,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { runsService } from "@/services"
import { useAppStore } from "@/store"
import { useAuth } from "@/contexts/AuthContext"
import { cn } from "@/utils/utils"
import type { NodeData } from "@/types"

const USD_TO_INR = 95

const statusConfig: Record<
  string,
  { icon: React.ElementType; color: string; badge: "default" | "secondary" | "success" | "destructive" | "warning" | "muted"; animate?: boolean }
> = {
  pending: { icon: Circle, color: "text-muted-foreground", badge: "muted" },
  idle: { icon: Circle, color: "text-muted-foreground", badge: "muted" },
  running: { icon: Loader2, color: "text-foreground", badge: "default", animate: true },
  completed: { icon: CheckCircle2, color: "text-success", badge: "success" },
  failed: { icon: XCircle, color: "text-destructive", badge: "destructive" },
  stale: { icon: AlertCircle, color: "text-warning", badge: "warning" },
}

interface NodeDetailPanelProps {
  runId: string
  nodeId: string
}

export function NodeDetailPanel({ runId, nodeId }: NodeDetailPanelProps) {
  const setSelectedNodeId = useAppStore((s) => s.setSelectedNodeId)
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const handleCopy = useCallback((text: string, id: string) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopiedId(id)
      setTimeout(() => setCopiedId(null), 2000)
    })
  }, [])
  const auth = useAuth()
  const canQueryRun = !auth.isConfigured || auth.isAuthenticated

  const { data: runData, isLoading } = useQuery({
    queryKey: ["run", runId],
    queryFn: () => runsService.get(runId),
    enabled: canQueryRun,
  })

  const node = runData?.graph?.nodes.find((n) => n.id === nodeId)
  const nodeData = node?.data as NodeData | undefined

  if (isLoading) {
    return (
      <div className="h-full p-4 flex items-center justify-center text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" />
      </div>
    )
  }

  if (!nodeData) {
    return (
      <div className="h-full p-4 flex items-center justify-center text-muted-foreground">
        Node not found
      </div>
    )
  }

  const config = statusConfig[nodeData.status] || statusConfig.pending
  const StatusIcon = config.icon

  // Parse output if it's a JSON string
  let parsedOutput: Record<string, unknown> | string = nodeData.output
  if (typeof nodeData.output === "string" && nodeData.output.startsWith("{")) {
    try {
      parsedOutput = JSON.parse(nodeData.output)
    } catch {
      // Keep as string
    }
  }

  return (
    <div className="h-full flex flex-col backdrop-blur-glass bg-card/80">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border/40">
        <div className="flex items-center gap-2.5">
          <StatusIcon
            className={cn(
              "h-4 w-4",
              config.color,
              config.animate && "animate-spin"
            )}
            strokeWidth={2}
          />
          <span className="font-medium text-sm">{nodeData.label}</span>
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 text-muted-foreground hover:text-foreground"
          onClick={() => setSelectedNodeId(null)}
          aria-label="Close node detail panel"
        >
          <X className="h-3.5 w-3.5" strokeWidth={1.75} />
        </Button>
      </div>

      {/* Metadata */}
      <div className="px-4 py-3 space-y-2 border-b border-border/40">
        <div className="flex items-center justify-between">
          <Badge variant="secondary" className="text-xs font-normal">
            {nodeData.type}
          </Badge>
          {nodeData.execution_time != null && (
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Clock className="h-3 w-3" strokeWidth={1.75} />
              <span className="font-mono">{(nodeData.execution_time / 1000).toFixed(2)}s</span>
            </div>
          )}
        </div>
        {nodeData.reads.length > 0 && (
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <ArrowLeft className="h-3 w-3" strokeWidth={1.75} />
            <span>Reads: {nodeData.reads.join(", ")}</span>
          </div>
        )}
        {nodeData.writes.length > 0 && (
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <ArrowRight className="h-3 w-3" strokeWidth={1.75} />
            <span>Writes: {nodeData.writes.join(", ")}</span>
          </div>
        )}
        {nodeData.cost > 0 && (
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <DollarSign className="h-3 w-3" strokeWidth={1.75} />
            <span className="font-mono">${nodeData.cost.toFixed(4)} (₹{(nodeData.cost * USD_TO_INR).toFixed(2)})</span>
          </div>
        )}
      </div>

      {/* Tabs */}
      <Tabs defaultValue="output" className="flex-1 flex flex-col min-h-0">
        <TabsList className="mx-4 mt-3 h-8 p-0.5 bg-muted/30 backdrop-blur-xs">
          <TabsTrigger value="output" className="text-xs h-7">Output</TabsTrigger>
          {nodeData.inputs && Object.keys(nodeData.inputs).length > 0 && (
            <TabsTrigger value="input" className="text-xs h-7">Input</TabsTrigger>
          )}
          <TabsTrigger value="prompt" className="text-xs h-7">Prompt</TabsTrigger>
          {nodeData.iterations && nodeData.iterations.length > 0 && (
            <TabsTrigger value="iterations" className="text-xs h-7">
              Iterations ({nodeData.iterations.length})
            </TabsTrigger>
          )}
          {nodeData.error && <TabsTrigger value="error" className="text-xs h-7">Error</TabsTrigger>}
        </TabsList>

        <ScrollArea className="flex-1">
          <TabsContent value="output" className="p-4 m-0">
            <CopyBlock
              text={typeof parsedOutput === "object" ? JSON.stringify(parsedOutput, null, 2) : String(parsedOutput)}
              id="output"
              copiedId={copiedId}
              onCopy={handleCopy}
            />
          </TabsContent>

          {nodeData.inputs && Object.keys(nodeData.inputs).length > 0 && (
            <TabsContent value="input" className="p-4 m-0">
              <div className="space-y-3">
                {Object.entries(nodeData.inputs).map(([key, value]) => (
                  <div key={key} className="border border-border/40 rounded-md p-3 bg-muted/15 backdrop-blur-xs">
                    <p className="font-medium text-xs text-muted-foreground mb-2">{key}</p>
                    <CopyBlock
                      text={typeof value === "object" ? JSON.stringify(value, null, 2) : String(value ?? "")}
                      id={`input-${key}`}
                      copiedId={copiedId}
                      onCopy={handleCopy}
                    />
                  </div>
                ))}
              </div>
            </TabsContent>
          )}

          <TabsContent value="prompt" className="p-4 m-0">
            <div className="space-y-4">
              {nodeData.description && (
                <div>
                  <p className="text-xs font-medium text-muted-foreground mb-1.5">
                    Description
                  </p>
                  <p className="text-sm leading-relaxed">{nodeData.description}</p>
                </div>
              )}
              {nodeData.prompt && (
                <div>
                  <p className="text-xs font-medium text-muted-foreground mb-1.5">
                    Prompt
                  </p>
                  <CopyBlock text={nodeData.prompt} id="prompt" copiedId={copiedId} onCopy={handleCopy} />
                </div>
              )}
            </div>
          </TabsContent>

          {nodeData.iterations && nodeData.iterations.length > 0 && (
            <TabsContent value="iterations" className="p-4 m-0">
              <div className="space-y-3">
                {nodeData.iterations.map((iter, idx) => (
                  <div key={idx} className="border border-border/40 rounded-md p-3 bg-muted/15 backdrop-blur-xs">
                    <p className="font-medium text-xs text-muted-foreground mb-2">
                      Iteration {iter.iteration}
                    </p>
                    <CopyBlock
                      text={JSON.stringify(iter.output, null, 2)}
                      id={`iter-${idx}`}
                      copiedId={copiedId}
                      onCopy={handleCopy}
                    />
                    {iter.tool_result && (
                      <div className="mt-2.5">
                        <p className="text-xs text-muted-foreground mb-1.5">
                          Tool Result
                        </p>
                        <CopyBlock
                          text={iter.tool_result}
                          id={`iter-tool-${idx}`}
                          copiedId={copiedId}
                          onCopy={handleCopy}
                        />
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </TabsContent>
          )}

          {nodeData.error && (
            <TabsContent value="error" className="p-4 m-0">
              <div className="bg-destructive/5 border border-destructive/20 rounded-md p-3">
                <pre className="text-xs text-destructive whitespace-pre-wrap font-mono leading-relaxed">
                  {nodeData.error}
                </pre>
              </div>
            </TabsContent>
          )}
        </ScrollArea>
      </Tabs>
    </div>
  )
}

function CopyBlock({
  text,
  id,
  copiedId,
  onCopy,
}: {
  text: string
  id: string
  copiedId: string | null
  onCopy: (text: string, id: string) => void
}) {
  return (
    <div className="relative group">
      <button
        onClick={() => onCopy(text, id)}
        className="absolute top-2 right-2 p-1.5 rounded-md bg-background/80 border border-border/40 text-muted-foreground hover:text-foreground opacity-0 group-hover:opacity-100 transition-opacity z-10"
        aria-label="Copy to clipboard"
      >
        {copiedId === id ? (
          <Check className="h-3.5 w-3.5 text-success" strokeWidth={2} />
        ) : (
          <Copy className="h-3.5 w-3.5" strokeWidth={1.75} />
        )}
      </button>
      <pre className="text-xs bg-muted/30 backdrop-blur-xs p-3 rounded-md border border-border/40 font-mono leading-relaxed whitespace-pre-wrap break-all">
        {text}
      </pre>
    </div>
  )
}
