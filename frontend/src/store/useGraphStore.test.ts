import { describe, it, expect, beforeEach } from 'vitest'
import { useGraphStore } from './useGraphStore'
import type { Node, Edge } from '@xyflow/react'

describe('useGraphStore', () => {
  const mockNodes: Node[] = [
    { id: 'node-1', position: { x: 0, y: 0 }, data: { label: 'Node 1', status: 'pending' } },
    { id: 'node-2', position: { x: 100, y: 0 }, data: { label: 'Node 2', status: 'pending' } },
    { id: 'node-3', position: { x: 200, y: 0 }, data: { label: 'Node 3', status: 'pending' } },
  ]

  const mockEdges: Edge[] = [
    { id: 'edge-1-2', source: 'node-1', target: 'node-2' },
    { id: 'edge-2-3', source: 'node-2', target: 'node-3' },
  ]

  beforeEach(() => {
    // Reset store to initial state
    useGraphStore.setState({
      nodes: [],
      edges: [],
    })
  })

  describe('initial state', () => {
    it('starts with empty nodes', () => {
      expect(useGraphStore.getState().nodes).toEqual([])
    })

    it('starts with empty edges', () => {
      expect(useGraphStore.getState().edges).toEqual([])
    })
  })

  describe('setNodes', () => {
    it('sets nodes array', () => {
      useGraphStore.getState().setNodes(mockNodes)
      expect(useGraphStore.getState().nodes).toEqual(mockNodes)
    })

    it('replaces existing nodes', () => {
      useGraphStore.getState().setNodes(mockNodes)

      const newNodes: Node[] = [
        { id: 'new-1', position: { x: 0, y: 0 }, data: { label: 'New' } },
      ]
      useGraphStore.getState().setNodes(newNodes)

      expect(useGraphStore.getState().nodes).toEqual(newNodes)
      expect(useGraphStore.getState().nodes).toHaveLength(1)
    })

    it('can set empty array', () => {
      useGraphStore.getState().setNodes(mockNodes)
      useGraphStore.getState().setNodes([])
      expect(useGraphStore.getState().nodes).toEqual([])
    })
  })

  describe('setEdges', () => {
    it('sets edges array', () => {
      useGraphStore.getState().setEdges(mockEdges)
      expect(useGraphStore.getState().edges).toEqual(mockEdges)
    })

    it('replaces existing edges', () => {
      useGraphStore.getState().setEdges(mockEdges)

      const newEdges: Edge[] = [
        { id: 'new-edge', source: 'a', target: 'b' },
      ]
      useGraphStore.getState().setEdges(newEdges)

      expect(useGraphStore.getState().edges).toEqual(newEdges)
    })
  })

  describe('updateNodeStatus', () => {
    beforeEach(() => {
      useGraphStore.getState().setNodes(mockNodes)
    })

    it('updates status of specific node', () => {
      useGraphStore.getState().updateNodeStatus('node-1', 'running')

      const node = useGraphStore.getState().nodes.find((n) => n.id === 'node-1')
      expect(node?.data.status).toBe('running')
    })

    it('does not affect other nodes', () => {
      useGraphStore.getState().updateNodeStatus('node-1', 'completed')

      const node2 = useGraphStore.getState().nodes.find((n) => n.id === 'node-2')
      expect(node2?.data.status).toBe('pending')
    })

    it('preserves other node data', () => {
      useGraphStore.getState().updateNodeStatus('node-1', 'error')

      const node = useGraphStore.getState().nodes.find((n) => n.id === 'node-1')
      expect(node?.data.label).toBe('Node 1')
      expect(node?.data.status).toBe('error')
    })

    it('handles non-existent node gracefully', () => {
      // Should not throw, just no-op
      useGraphStore.getState().updateNodeStatus('non-existent', 'running')
      expect(useGraphStore.getState().nodes).toHaveLength(3)
    })
  })

  describe('updateNodeData', () => {
    beforeEach(() => {
      useGraphStore.getState().setNodes(mockNodes)
    })

    it('updates node data with new properties', () => {
      useGraphStore.getState().updateNodeData('node-1', { output: 'result' })

      const node = useGraphStore.getState().nodes.find((n) => n.id === 'node-1')
      expect(node?.data.output).toBe('result')
    })

    it('merges with existing data', () => {
      useGraphStore.getState().updateNodeData('node-1', { output: 'result' })
      useGraphStore.getState().updateNodeData('node-1', { cost: 0.05 })

      const node = useGraphStore.getState().nodes.find((n) => n.id === 'node-1')
      expect(node?.data.output).toBe('result')
      expect(node?.data.cost).toBe(0.05)
      expect(node?.data.label).toBe('Node 1')
    })

    it('can update multiple properties at once', () => {
      useGraphStore.getState().updateNodeData('node-2', {
        status: 'completed',
        output: 'done',
        tokens: 100,
      })

      const node = useGraphStore.getState().nodes.find((n) => n.id === 'node-2')
      expect(node?.data.status).toBe('completed')
      expect(node?.data.output).toBe('done')
      expect(node?.data.tokens).toBe(100)
    })

    it('does not affect other nodes', () => {
      useGraphStore.getState().updateNodeData('node-1', { custom: 'value' })

      const node2 = useGraphStore.getState().nodes.find((n) => n.id === 'node-2')
      expect(node2?.data.custom).toBeUndefined()
    })

    it('handles non-existent node gracefully', () => {
      useGraphStore.getState().updateNodeData('non-existent', { data: 'test' })
      expect(useGraphStore.getState().nodes).toHaveLength(3)
    })
  })

  describe('clearGraph', () => {
    it('clears all nodes and edges', () => {
      useGraphStore.getState().setNodes(mockNodes)
      useGraphStore.getState().setEdges(mockEdges)

      expect(useGraphStore.getState().nodes).toHaveLength(3)
      expect(useGraphStore.getState().edges).toHaveLength(2)

      useGraphStore.getState().clearGraph()

      expect(useGraphStore.getState().nodes).toEqual([])
      expect(useGraphStore.getState().edges).toEqual([])
    })

    it('is idempotent', () => {
      useGraphStore.getState().clearGraph()
      useGraphStore.getState().clearGraph()

      expect(useGraphStore.getState().nodes).toEqual([])
      expect(useGraphStore.getState().edges).toEqual([])
    })
  })

  describe('complex workflows', () => {
    it('simulates agent execution flow', () => {
      // Setup graph
      useGraphStore.getState().setNodes(mockNodes)
      useGraphStore.getState().setEdges(mockEdges)

      // Start node 1
      useGraphStore.getState().updateNodeStatus('node-1', 'running')
      expect(useGraphStore.getState().nodes[0].data.status).toBe('running')

      // Complete node 1, start node 2
      useGraphStore.getState().updateNodeData('node-1', {
        status: 'completed',
        output: 'Result 1',
        cost: 0.01,
      })
      useGraphStore.getState().updateNodeStatus('node-2', 'running')

      // Verify state
      const nodes = useGraphStore.getState().nodes
      expect(nodes.find((n) => n.id === 'node-1')?.data.status).toBe('completed')
      expect(nodes.find((n) => n.id === 'node-2')?.data.status).toBe('running')
      expect(nodes.find((n) => n.id === 'node-3')?.data.status).toBe('pending')
    })
  })
})
