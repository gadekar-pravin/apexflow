import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react"
import { Activity, BarChart3, Loader2 } from "lucide-react"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { ReasoningSidebar } from "./ReasoningSidebar"
import type { AgentChatMessage } from "@/types"

const VisualizationCanvas = lazy(() =>
  import("./VisualizationCanvas").then((m) => ({ default: m.VisualizationCanvas }))
)

interface RightPanelProps {
  messages: AgentChatMessage[]
  activeRunId: string | null
  sessionId: string | null
}

export function RightPanel({ messages, activeRunId, sessionId }: RightPanelProps) {
  const [activeTab, setActiveTab] = useState<string>("activity")
  const prevMessageCountRef = useRef(messages.length)

  const hasCharts = useMemo(() => {
    return messages.some((msg) => {
      const viz = msg.metadata?.visualizations
      return Array.isArray(viz) && viz.length > 0
    })
  }, [messages])

  // Auto-switch to Charts tab when a new assistant message arrives with visualizations
  useEffect(() => {
    if (messages.length <= prevMessageCountRef.current) {
      prevMessageCountRef.current = messages.length
      return
    }
    prevMessageCountRef.current = messages.length

    const lastMsg = messages[messages.length - 1]
    if (
      lastMsg?.role === "assistant" &&
      Array.isArray(lastMsg.metadata?.visualizations) &&
      (lastMsg.metadata?.visualizations as unknown[]).length > 0
    ) {
      setActiveTab("charts")
    }
  }, [messages])

  // Reset to activity tab on session change
  useEffect(() => {
    setActiveTab("activity")
  }, [sessionId])

  return (
    <Tabs value={activeTab} onValueChange={setActiveTab} className="flex flex-col h-full">
      <div className="shrink-0 px-3 pt-3">
        <TabsList className="w-full">
          <TabsTrigger value="activity" className="flex-1 gap-1.5 text-xs">
            <Activity className="h-3.5 w-3.5" />
            Activity
          </TabsTrigger>
          <TabsTrigger value="charts" className="flex-1 gap-1.5 text-xs">
            <BarChart3 className="h-3.5 w-3.5" />
            Charts
            {hasCharts && (
              <span className="ml-1 h-1.5 w-1.5 rounded-full bg-primary" />
            )}
          </TabsTrigger>
        </TabsList>
      </div>

      <TabsContent value="activity" className="flex-1 min-h-0 mt-0">
        <ReasoningSidebar activeRunId={activeRunId} sessionId={sessionId} />
      </TabsContent>

      <TabsContent value="charts" className="flex-1 min-h-0 mt-0">
        <Suspense
          fallback={
            <div className="flex h-full items-center justify-center">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          }
        >
          <VisualizationCanvas messages={messages} />
        </Suspense>
      </TabsContent>
    </Tabs>
  )
}
