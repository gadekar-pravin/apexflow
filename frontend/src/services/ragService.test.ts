import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ragService } from './ragService'

vi.mock('./api', () => ({
  fetchAPI: vi.fn(),
  getAPIUrl: vi.fn((endpoint: string) => `http://localhost:8000${endpoint}`),
}))

import { fetchAPI } from './api'

const mockFetchAPI = vi.mocked(fetchAPI)

describe('ragService', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe('getDocuments', () => {
    it('fetches document list', async () => {
      const docs = { documents: [{ id: 'doc1', filename: 'doc1.txt' }] }
      mockFetchAPI.mockResolvedValueOnce(docs)

      const result = await ragService.getDocuments()

      expect(mockFetchAPI).toHaveBeenCalledWith('/api/rag/documents')
      expect(result).toEqual(docs)
    })
  })

  describe('search', () => {
    it('performs semantic search via POST', async () => {
      const searchResult = { results: [{ chunk_id: 'c1', document_id: 'd1', content: 'match', chunk_index: 0, rrf_score: 0.9, vector_score: 0.8, text_score: 0.7 }] }
      mockFetchAPI.mockResolvedValueOnce(searchResult)

      await ragService.search('test query')

      expect(mockFetchAPI).toHaveBeenCalledWith('/api/rag/search', {
        method: 'POST',
        body: JSON.stringify({ query: 'test query', limit: 10 }),
      })
    })

    it('accepts custom limit', async () => {
      mockFetchAPI.mockResolvedValueOnce({ results: [] })

      await ragService.search('query', 5)

      expect(mockFetchAPI).toHaveBeenCalledWith('/api/rag/search', {
        method: 'POST',
        body: JSON.stringify({ query: 'query', limit: 5 }),
      })
    })
  })

  describe('stubbed methods', () => {
    it('keywordSearch throws not available', async () => {
      await expect(ragService.keywordSearch('test')).rejects.toThrow('Not available in v2')
    })

    it('ripgrepSearch throws not available', async () => {
      await expect(ragService.ripgrepSearch('test')).rejects.toThrow('Not available in v2')
    })

    it('getDocumentChunks throws not available', async () => {
      await expect(ragService.getDocumentChunks('/path')).rejects.toThrow('Not available in v2')
    })

    it('getDocumentContentUrl returns empty string', () => {
      expect(ragService.getDocumentContentUrl('/path')).toBe('')
    })

    it('getIndexingStatus throws not available', async () => {
      await expect(ragService.getIndexingStatus()).rejects.toThrow('Not available in v2')
    })

    it('createFolder throws not available', async () => {
      await expect(ragService.createFolder('/path')).rejects.toThrow('Not available in v2')
    })

    it('createFile throws not available', async () => {
      await expect(ragService.createFile('/path')).rejects.toThrow('Not available in v2')
    })

    it('saveFile throws not available', async () => {
      await expect(ragService.saveFile('/path', 'content')).rejects.toThrow('Not available in v2')
    })

    it('deleteItem throws not available', async () => {
      await expect(ragService.deleteItem('/path')).rejects.toThrow('Not available in v2')
    })

    it('renameItem throws not available', async () => {
      await expect(ragService.renameItem('/old', '/new')).rejects.toThrow('Not available in v2')
    })

    it('uploadFile throws not available', async () => {
      const file = new File(['content'], 'test.txt', { type: 'text/plain' })
      await expect(ragService.uploadFile(file)).rejects.toThrow('Not available in v2')
    })
  })

  describe('reindex', () => {
    it('triggers full reindex', async () => {
      mockFetchAPI.mockResolvedValueOnce({ reindexed: [] })

      await ragService.reindex()

      expect(mockFetchAPI).toHaveBeenCalledWith('/api/rag/reindex', {
        method: 'POST',
        body: JSON.stringify({}),
      })
    })

    it('reindexes specific document by ID', async () => {
      mockFetchAPI.mockResolvedValueOnce({ reindexed: [] })

      await ragService.reindex('doc-123')

      expect(mockFetchAPI).toHaveBeenCalledWith('/api/rag/reindex', {
        method: 'POST',
        body: JSON.stringify({ doc_id: 'doc-123' }),
      })
    })
  })

  describe('chat sessions', () => {
    describe('getChatSessions', () => {
      it('fetches sessions for target', async () => {
        const sessions = { status: 'ok', sessions: [{ id: 's1', title: 'Chat 1' }] }
        mockFetchAPI.mockResolvedValueOnce(sessions)

        const result = await ragService.getChatSessions('rag', '/doc.md')

        expect(mockFetchAPI).toHaveBeenCalledWith(
          '/api/chat/sessions?target_type=rag&target_id=%2Fdoc.md'
        )
        expect(result.sessions).toHaveLength(1)
      })
    })

    describe('getChatSession', () => {
      it('fetches specific session and merges messages', async () => {
        const messages = [{ id: 'm1', role: 'user', content: 'hello', timestamp: 1 }]
        const apiResponse = {
          status: 'ok',
          session: { id: 's1' },
          messages,
        }
        mockFetchAPI.mockResolvedValueOnce(apiResponse)

        const result = await ragService.getChatSession('s1', 'notes', 'note-1')

        expect(mockFetchAPI).toHaveBeenCalledWith('/api/chat/sessions/s1')
        expect(result.session.messages).toEqual(messages)
      })
    })

    describe('saveChatSession', () => {
      it('saves session with v2 format', async () => {
        const session = {
          id: 's1',
          messages: [],
          target_type: 'rag' as const,
          target_id: '/doc',
          title: 'Chat',
          created_at: 0,
          updated_at: 0,
        }
        mockFetchAPI.mockResolvedValueOnce({ status: 'ok', session })

        await ragService.saveChatSession(session as any)

        expect(mockFetchAPI).toHaveBeenCalledWith('/api/chat/sessions', {
          method: 'POST',
          body: JSON.stringify({
            target_type: 'rag',
            target_id: '/doc',
            title: 'Chat',
          }),
        })
      })
    })

    describe('deleteChatSession', () => {
      it('deletes session', async () => {
        mockFetchAPI.mockResolvedValueOnce({ status: 'deleted' })

        await ragService.deleteChatSession('s1', 'ide', 'file.ts')

        expect(mockFetchAPI).toHaveBeenCalledWith('/api/chat/sessions/s1', {
          method: 'DELETE',
        })
      })
    })
  })
})
