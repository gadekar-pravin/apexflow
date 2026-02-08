import { create } from "zustand"
import type { Node, Edge } from "@xyflow/react"

interface GraphState {
  nodes: Node[]
  edges: Edge[]
  setNodes: (nodes: Node[]) => void
  setEdges: (edges: Edge[]) => void
  updateNodeStatus: (nodeId: string, status: string) => void
  updateNodeData: (nodeId: string, data: Record<string, unknown>) => void
  clearGraph: () => void
}

export const useGraphStore = create<GraphState>((set) => ({
  nodes: [],
  edges: [],

  setNodes: (nodes) => set({ nodes }),
  setEdges: (edges) => set({ edges }),

  updateNodeStatus: (nodeId, status) =>
    set((state) => ({
      nodes: state.nodes.map((node) =>
        node.id === nodeId
          ? { ...node, data: { ...node.data, status } }
          : node
      ),
    })),

  updateNodeData: (nodeId, data) =>
    set((state) => ({
      nodes: state.nodes.map((node) =>
        node.id === nodeId
          ? { ...node, data: { ...node.data, ...data } }
          : node
      ),
    })),

  clearGraph: () => set({ nodes: [], edges: [] }),
}))
