import { lazy, Suspense } from "react"
import { Loader2 } from "lucide-react"
import type { VisualizationSpec } from "@/types"

const ChartCard = lazy(() =>
  import("./ChartCard").then((m) => ({ default: m.ChartCard }))
)

interface InlineChartsProps {
  visualizations: VisualizationSpec[]
  messageId: string
}

export function InlineCharts({ visualizations, messageId }: InlineChartsProps) {
  if (visualizations.length === 0) return null

  return (
    <div className="mt-3 space-y-3">
      <Suspense
        fallback={
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        }
      >
        {visualizations
          .filter((spec): spec is VisualizationSpec => spec != null && typeof spec === "object")
          .map((spec) => (
            <ChartCard key={`${messageId}:${spec.id}`} spec={spec} />
          ))}
      </Suspense>
    </div>
  )
}
