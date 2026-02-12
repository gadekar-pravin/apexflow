import { RunCreator, RunList } from "@/components/runs"
import { GraphView, NodeDetailPanel } from "@/components/graph"
import { ResizablePanel } from "@/components/ui/resizable-panel"
import { useAppStore } from "@/store"
import { Hexagon } from "lucide-react"

export function DashboardPage() {
  const { selectedRunId, selectedNodeId } = useAppStore()

  return (
    <div className="flex h-full">
      {/* Left sidebar - Run list */}
      <ResizablePanel
        defaultWidth={288}
        minWidth={200}
        maxWidth={600}
        storageKey="apexflow.dashboard.runsWidth"
        className="border-r border-border/40 flex flex-col backdrop-blur-glass bg-sidebar/40"
      >
        <div className="px-4 pt-5 pb-4">
          <h2 className="text-sm font-medium text-foreground mb-3">Agent Runs</h2>
          <RunCreator />
        </div>
        <div className="mx-4 divider-fade" />
        <div className="flex-1 overflow-hidden">
          <RunList />
        </div>
      </ResizablePanel>

      {/* Main content - Graph view */}
      <div className="flex-1 flex flex-col bg-background">
        {selectedRunId ? (
          <div className="flex-1 flex">
            <div className="flex-1">
              <GraphView runId={selectedRunId} />
            </div>
            {selectedNodeId && (
              <ResizablePanel
                defaultWidth={380}
                minWidth={280}
                maxWidth={700}
                storageKey="apexflow.dashboard.nodeDetailWidth"
                side="left"
                className="border-l border-border/40"
              >
                <NodeDetailPanel runId={selectedRunId} nodeId={selectedNodeId} />
              </ResizablePanel>
            )}
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center max-w-md px-8">
              <div className="flex justify-center mb-6">
                <div className="h-14 w-14 rounded-xl backdrop-blur-glass bg-primary/10 border border-primary/20 flex items-center justify-center shadow-glass-glow glow-on-hover transition-all duration-300">
                  <Hexagon className="h-7 w-7 text-primary" strokeWidth={1.5} />
                </div>
              </div>
              <h2 className="text-xl font-semibold tracking-tight mb-2">
                Welcome to Cortex
              </h2>
              <p className="text-muted-foreground text-sm leading-relaxed">
                Create a new run or select an existing one from the panel to view
                the agent execution graph. Watch as agents collaborate in real-time
                to complete your request.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
