import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { fetchAPI, getAPIUrl, API_URL, ApiError, isUnauthorizedError } from './api'

describe('api', () => {
  const mockFetch = vi.fn()

  beforeEach(() => {
    vi.stubGlobal('fetch', mockFetch)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe('fetchAPI', () => {
    it('makes GET request to correct URL', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        text: () => Promise.resolve(JSON.stringify({ data: 'test' })),
      })

      await fetchAPI('/test-endpoint')

      expect(mockFetch).toHaveBeenCalledWith(
        `${API_URL}/test-endpoint`,
        expect.objectContaining({
          headers: { 'Content-Type': 'application/json' },
        })
      )
    })

    it('makes POST request with body', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        text: () => Promise.resolve(JSON.stringify({ status: 'ok' })),
      })

      await fetchAPI('/create', {
        method: 'POST',
        body: JSON.stringify({ name: 'test' }),
      })

      expect(mockFetch).toHaveBeenCalledWith(
        `${API_URL}/create`,
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ name: 'test' }),
          headers: { 'Content-Type': 'application/json' },
        })
      )
    })

    it('returns parsed JSON response', async () => {
      const mockData = { id: 1, name: 'test' }
      mockFetch.mockResolvedValueOnce({
        ok: true,
        text: () => Promise.resolve(JSON.stringify(mockData)),
      })

      const result = await fetchAPI('/data')

      expect(result).toEqual(mockData)
    })

    it('throws error on non-ok response with detail', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 404,
        json: () => Promise.resolve({ detail: 'Not found' }),
      })

      await expect(fetchAPI('/missing')).rejects.toThrow('Not found')
    })

    it('throws ApiError with status code', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: () => Promise.resolve({ detail: 'Invalid or expired token' }),
      })

      try {
        await fetchAPI('/api/runs')
        expect.fail('Expected fetchAPI to throw')
      } catch (error) {
        expect(error).toBeInstanceOf(ApiError)
        expect((error as ApiError).status).toBe(401)
        expect(isUnauthorizedError(error)).toBe(true)
      }
    })

    it('throws error with status code when no detail', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
        json: () => Promise.reject(new Error('Invalid JSON')),
      })

      await expect(fetchAPI('/error')).rejects.toThrow('Internal Server Error')
    })

    it('merges custom headers with default', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        text: () => Promise.resolve(JSON.stringify({})),
      })

      await fetchAPI('/auth', {
        headers: { Authorization: 'Bearer token' },
      })

      expect(mockFetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: {
            'Content-Type': 'application/json',
            Authorization: 'Bearer token',
          },
        })
      )
    })
  })

  describe('getAPIUrl', () => {
    it('constructs full URL from endpoint', () => {
      expect(getAPIUrl('/runs')).toBe(`${API_URL}/runs`)
    })

    it('handles endpoints with query params', () => {
      expect(getAPIUrl('/search?q=test')).toBe(`${API_URL}/search?q=test`)
    })
  })
})
