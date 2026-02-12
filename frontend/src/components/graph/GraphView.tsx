import { useCallback, useEffect } from "react"
import {
  ReactFlow,
  Controls,
  Background,
  useNodesState,
  useEdgesState,
  BackgroundVariant,
  type Node,
  type Edge,
} from "@xyflow/react"
import "@xyflow/react/dist/style.css"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { Loader2 } from "lucide-react"
import { AgentNode } from "./AgentNode"
import { CustomEdge } from "./CustomEdge"
import { runsService } from "@/services"
import { useAppStore } from "@/store"
import { useAuth } from "@/contexts/AuthContext"
import { useSSESubscription } from "@/contexts/SSEContext"
import type { SSEEvent, GraphNode, GraphEdge } from "@/types"

const nodeTypes = {
  agentNode: AgentNode,
}

const edgeTypes = {
  custom: CustomEdge,
}

interface GraphViewProps {
  runId: string
}

// Convert backend GraphNode to ReactFlow Node
function toReactFlowNode(node: GraphNode, index: number): Node {
  return {
    id: node.id,
    type: node.type,
    position: node.position,
    data: { ...(node.data as unknown as Record<string, unknown>), _nodeIndex: index },
  }
}

// Convert backend GraphEdge to ReactFlow Edge
function toReactFlowEdge(edge: GraphEdge): Edge {
  return {
    id: edge.id,
    source: edge.source,
    target: edge.target,
    type: edge.type,
    animated: edge.animated,
    style: edge.style,
  }
}

export function GraphView({ runId }: GraphViewProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])
  const setSelectedNodeId = useAppStore((s) => s.setSelectedNodeId)
  const queryClient = useQueryClient()
  const auth = useAuth()
  const canQueryRun = !auth.isConfigured || auth.isAuthenticated

  const { data, isLoading, error } = useQuery({
    queryKey: ["run", runId],
    queryFn: () => runsService.get(runId),
    enabled: canQueryRun,
    refetchInterval: (query) =>
      query.state.data?.status === "running" ? 2000 : false,
  })

  // Update nodes and edges when data changes
  useEffect(() => {
    if (data?.graph) {
      setNodes(data.graph.nodes.map((node, index) => toReactFlowNode(node, index)))
      setEdges(data.graph.edges.map(toReactFlowEdge))
    }
  }, [data, setNodes, setEdges])

  // Handle SSE events for real-time updates (using shared connection)
  const handleSSEEvent = useCallback(
    (event: SSEEvent) => {
      // Invalidate run query on relevant events
      if (
        event.type === "context_updated" ||
        event.type === "step_start" ||
        event.type === "success" ||
        event.type === "error"
      ) {
        queryClient.invalidateQueries({ queryKey: ["run", runId] })
        queryClient.invalidateQueries({ queryKey: ["runs"] })
      }
    },
    [queryClient, runId]
  )
  useSSESubscription(handleSSEEvent)

  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      setSelectedNodeId(node.id)
    },
    [setSelectedNodeId]
  )

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center text-destructive">
        Failed to load graph: {(error as Error).message}
      </div>
    )
  }

  if (!data?.graph) {
    return (
      <div className="flex h-full items-center justify-center text-muted-foreground">
        {data?.status === "running" ? (
          <Loader2 className="h-8 w-8 animate-spin" />
        ) : (
          <span>No graph data available</span>
        )}
      </div>
    )
  }

  return (
    <div className="h-full w-full bg-background">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={onNodeClick}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        minZoom={0.1}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
        defaultEdgeOptions={{
          type: "custom",
        }}
      >
        <Controls position="top-right" className="!shadow-[0_4px_20px_-2px_rgba(0,0,0,0.05)] !bg-white dark:!bg-slate-800 !border-border/40 !rounded-xl" />
        <Background
          variant={BackgroundVariant.Dots}
          gap={20}
          size={1.5}
          color="hsl(var(--border) / 0.6)"
        />
      </ReactFlow>
    </div>
  )
}
