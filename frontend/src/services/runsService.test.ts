import { describe, it, expect, vi, beforeEach } from 'vitest'
import { runsService } from './runsService'

vi.mock('./api', () => ({
  fetchAPI: vi.fn(),
}))

import { fetchAPI } from './api'

const mockFetchAPI = vi.mocked(fetchAPI)

describe('runsService', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('create', () => {
    it('creates a new run with query', async () => {
      const request = { query: 'Analyze this data' }
      const response = { id: 'run-123', status: 'pending' }
      mockFetchAPI.mockResolvedValueOnce(response)

      const result = await runsService.create(request)

      expect(mockFetchAPI).toHaveBeenCalledWith('/api/runs/execute', {
        method: 'POST',
        body: JSON.stringify(request),
      })
      expect(result).toEqual(response)
    })

    it('creates run with optional agent_type', async () => {
      const request = {
        query: 'Search the web',
        agent_type: 'browser',
      }
      mockFetchAPI.mockResolvedValueOnce({ id: 'run-456' })

      await runsService.create(request)

      expect(mockFetchAPI).toHaveBeenCalledWith('/api/runs/execute', {
        method: 'POST',
        body: JSON.stringify(request),
      })
    })
  })

  describe('list', () => {
    it('returns all runs', async () => {
      const runs = [
        { id: 'run-1', task: 'Task 1', status: 'completed' },
        { id: 'run-2', task: 'Task 2', status: 'running' },
      ]
      mockFetchAPI.mockResolvedValueOnce(runs)

      const result = await runsService.list()

      expect(mockFetchAPI).toHaveBeenCalledWith('/api/runs')
      expect(result).toEqual(runs)
    })
  })

  describe('get', () => {
    it('fetches run details by ID', async () => {
      const runDetail = {
        id: 'run-123',
        task: 'Test task',
        status: 'completed',
        graph: { nodes: [], edges: [] },
      }
      mockFetchAPI.mockResolvedValueOnce(runDetail)

      const result = await runsService.get('run-123')

      expect(mockFetchAPI).toHaveBeenCalledWith('/api/runs/run-123')
      expect(result).toEqual(runDetail)
    })
  })

  describe('stop', () => {
    it('stops a running execution', async () => {
      mockFetchAPI.mockResolvedValueOnce({ id: 'run-123', status: 'stopped' })

      const result = await runsService.stop('run-123')

      expect(mockFetchAPI).toHaveBeenCalledWith('/api/runs/run-123/stop', {
        method: 'POST',
      })
      expect(result.status).toBe('stopped')
    })
  })

  describe('delete', () => {
    it('deletes a run', async () => {
      mockFetchAPI.mockResolvedValueOnce({ id: 'run-123', status: 'deleted' })

      const result = await runsService.delete('run-123')

      expect(mockFetchAPI).toHaveBeenCalledWith('/api/runs/run-123', {
        method: 'DELETE',
      })
      expect(result.status).toBe('deleted')
    })
  })

  describe('provideInput', () => {
    it('sends user input to running agent', async () => {
      const input = { node_id: 'node-1', response: 'Yes, proceed' }
      mockFetchAPI.mockResolvedValueOnce({
        id: 'run-123',
        status: 'input_received',
      })

      const result = await runsService.provideInput('run-123', input)

      expect(mockFetchAPI).toHaveBeenCalledWith('/api/runs/run-123/input', {
        method: 'POST',
        body: JSON.stringify(input),
      })
      expect(result.status).toBe('input_received')
    })
  })

  describe('testAgent', () => {
    it('throws not available in v2', async () => {
      await expect(runsService.testAgent('run-123', 'node-1', 'input')).rejects.toThrow(
        'Not available in v2'
      )
    })
  })

  describe('saveAgentTest', () => {
    it('throws not available in v2', async () => {
      await expect(
        runsService.saveAgentTest('run-123', 'node-1', { output: 'test' })
      ).rejects.toThrow('Not available in v2')
    })
  })
})
