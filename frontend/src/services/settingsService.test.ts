import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { settingsService } from './settingsService'
import type { Settings } from '@/types'

// Mock fetchAPI
vi.mock('./api', () => ({
  fetchAPI: vi.fn(),
}))

import { fetchAPI } from './api'

const mockFetchAPI = vi.mocked(fetchAPI)

const mockSettings: Settings = {
  models: {
    embedding: 'text-embedding-004',
    semantic_chunking: 'gemini-2.5-flash-lite',
    image_captioning: 'gemini-2.5-flash-lite',
    memory_extraction: 'gemini-2.5-flash-lite',
    insights_provider: 'gemini',
  },
  rag: {
    chunk_size: 256,
    chunk_overlap: 40,
    max_chunk_length: 512,
    semantic_word_limit: 1024,
    top_k: 3,
  },
  agent: {
    model_provider: 'gemini',
    default_model: 'gemini-2.5-flash-lite',
    overrides: {},
    max_steps: 3,
    max_lifelines_per_step: 3,
    planning_mode: 'conservative',
    rate_limit_interval: 4.5,
    max_cost_per_run: 0.5,
    warn_at_cost: 0.25,
  },
  testing: {
    feedback_mode: 'with_permission',
    regenerate_on_type_changes: false,
    regenerate_on_docstring_changes: false,
    test_agent_model: 'phi4:latest',
  },
  remme: {
    extraction_prompt: 'test prompt',
  },
  gemini: {
    api_key_env: 'GEMINI_API_KEY',
  },
  news: {
    sources: [],
  },
}

describe('settingsService', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe('get', () => {
    it('fetches settings and extracts from response wrapper', async () => {
      mockFetchAPI.mockResolvedValueOnce({
        status: 'success',
        settings: mockSettings,
      })

      const result = await settingsService.get()

      expect(mockFetchAPI).toHaveBeenCalledWith('/api/settings')
      expect(result).toEqual(mockSettings)
    })

    it('correctly unwraps nested response structure', async () => {
      mockFetchAPI.mockResolvedValueOnce({
        status: 'success',
        settings: { ...mockSettings, agent: { ...mockSettings.agent, max_steps: 5 } },
      })

      const result = await settingsService.get()

      expect(result.agent.max_steps).toBe(5)
      expect(result).not.toHaveProperty('status')
    })
  })

  describe('update', () => {
    it('sends PUT request with settings wrapper', async () => {
      mockFetchAPI.mockResolvedValueOnce({ status: 'success' })

      const update = { agent: { max_steps: 5 } }
      await settingsService.update(update as Partial<Settings>)

      expect(mockFetchAPI).toHaveBeenCalledWith('/api/settings', {
        method: 'PUT',
        body: JSON.stringify({ settings: update }),
      })
    })
  })

  describe('reset', () => {
    it('sends POST request to reset endpoint', async () => {
      mockFetchAPI.mockResolvedValueOnce({ status: 'success' })

      await settingsService.reset()

      expect(mockFetchAPI).toHaveBeenCalledWith('/api/settings/reset', {
        method: 'POST',
      })
    })
  })

  describe('healthCheck', () => {
    it('returns health status from /liveness', async () => {
      const health = { status: 'ok' }
      mockFetchAPI.mockResolvedValueOnce(health)

      const result = await settingsService.healthCheck()

      expect(mockFetchAPI).toHaveBeenCalledWith('/liveness')
      expect(result).toEqual(health)
    })
  })

  describe('getMCPTools', () => {
    it('fetches skills list from v2 endpoint', async () => {
      const tools = [{ name: 'tool1', description: 'desc' }]
      mockFetchAPI.mockResolvedValueOnce(tools)

      const result = await settingsService.getMCPTools()

      expect(mockFetchAPI).toHaveBeenCalledWith('/api/skills')
      expect(result).toEqual([{ name: 'tool1', description: 'desc' }])
    })

    it('returns empty array on error', async () => {
      mockFetchAPI.mockRejectedValueOnce(new Error('Not found'))

      const result = await settingsService.getMCPTools()

      expect(result).toEqual([])
    })
  })

  describe('cron job operations', () => {
    const mockJob = {
      id: 'job-1',
      name: 'Test Job',
      cron: '0 * * * *',
      agent_type: 'browser',
      query: 'test',
    }

    it('getCronJobs fetches all jobs', async () => {
      mockFetchAPI.mockResolvedValueOnce([mockJob])

      const result = await settingsService.getCronJobs()

      expect(mockFetchAPI).toHaveBeenCalledWith('/api/cron/jobs')
      expect(result).toEqual([mockJob])
    })

    it('createCronJob sends POST with job data', async () => {
      mockFetchAPI.mockResolvedValueOnce(mockJob)
      const { id, ...jobData } = mockJob

      await settingsService.createCronJob(jobData)

      expect(mockFetchAPI).toHaveBeenCalledWith('/api/cron/jobs', {
        method: 'POST',
        body: JSON.stringify(jobData),
      })
    })

    it('updateCronJob throws not available in v2', async () => {
      await expect(
        settingsService.updateCronJob('job-1', { name: 'Updated' })
      ).rejects.toThrow('Not available in v2')
    })

    it('deleteCronJob sends DELETE request', async () => {
      mockFetchAPI.mockResolvedValueOnce({ status: 'deleted' })

      await settingsService.deleteCronJob('job-1')

      expect(mockFetchAPI).toHaveBeenCalledWith('/api/cron/jobs/job-1', {
        method: 'DELETE',
      })
    })

    it('runCronJob triggers immediate execution', async () => {
      mockFetchAPI.mockResolvedValueOnce({ status: 'running' })

      await settingsService.runCronJob('job-1')

      expect(mockFetchAPI).toHaveBeenCalledWith('/api/cron/jobs/job-1/trigger', {
        method: 'POST',
      })
    })
  })
})
