import { useMemo } from "react"
import { BarChart3 } from "lucide-react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { ChartCard } from "./ChartCard"
import type { AgentChatMessage, VisualizationSpec } from "@/types"

interface VisualizationCanvasProps {
  messages: AgentChatMessage[]
}

function isValidSpec(spec: unknown): spec is VisualizationSpec {
  if (!spec || typeof spec !== "object") return false
  const s = spec as Record<string, unknown>
  return (
    s.schema_version === 1 &&
    typeof s.id === "string" &&
    typeof s.title === "string" &&
    typeof s.chart_type === "string" &&
    ["bar", "line", "pie", "area"].includes(s.chart_type as string) &&
    Array.isArray(s.data) &&
    s.data.length > 0 &&
    typeof s.x_key === "string" &&
    Array.isArray(s.y_keys) &&
    s.y_keys.length > 0
  )
}

export function VisualizationCanvas({ messages }: VisualizationCanvasProps) {
  const charts = useMemo(() => {
    const result: Array<{ key: string; spec: VisualizationSpec }> = []
    for (const msg of messages) {
      const vizArray = msg.metadata?.visualizations
      if (!Array.isArray(vizArray)) continue
      for (const spec of vizArray) {
        if (isValidSpec(spec)) {
          result.push({ key: `${msg.id}:${spec.id}`, spec })
        }
      }
    }
    return result
  }, [messages])

  if (charts.length === 0) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <div className="text-center space-y-2">
          <BarChart3 className="h-8 w-8 text-muted-foreground/40 mx-auto" />
          <h3 className="text-sm font-semibold text-foreground">No charts yet</h3>
          <p className="text-xs text-muted-foreground max-w-[200px]">
            Charts will appear here when agent responses contain data visualizations.
          </p>
        </div>
      </div>
    )
  }

  return (
    <ScrollArea className="h-full">
      <div className="p-4 space-y-4">
        {charts.map(({ key, spec }) => (
          <ChartCard key={key} spec={spec} />
        ))}
      </div>
    </ScrollArea>
  )
}
