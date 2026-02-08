import { fetchAPI } from "./api"
import type {
  DocumentsResponse,
  SearchResponse,
  ChatSession,
  ChatSessionSummary,
} from "@/types"

export const ragService = {
  // Get document list
  async getDocuments(): Promise<DocumentsResponse> {
    return fetchAPI<DocumentsResponse>("/api/rag/documents")
  },

  // Semantic search (v2: POST with body instead of GET with query param)
  async search(query: string, limit: number = 10): Promise<SearchResponse> {
    return fetchAPI<SearchResponse>("/api/rag/search", {
      method: "POST",
      body: JSON.stringify({ query, limit }),
    })
  },

  // Keyword search (not available in v2)
  async keywordSearch(_query: string): Promise<{ status: string; matches: string[] }> {
    throw new Error("Not available in v2")
  },

  // Ripgrep search (not available in v2)
  async ripgrepSearch(
    _query: string,
    _options?: { regex?: boolean; case_sensitive?: boolean; target_dir?: string }
  ): Promise<never> {
    throw new Error("Not available in v2")
  },

  // Get document chunks (not available in v2)
  async getDocumentChunks(_path: string): Promise<never> {
    throw new Error("Not available in v2")
  },

  // Get document content URL (not available in v2)
  getDocumentContentUrl(_path: string): string {
    return ""
  },

  // Trigger reindex (v2: body is {doc_id?, limit?} instead of {path?, force?})
  async reindex(docId?: string, limit?: number): Promise<{ status: string; result: unknown }> {
    const params: Record<string, unknown> = {}
    if (docId) params.doc_id = docId
    if (limit) params.limit = limit
    return fetchAPI("/api/rag/reindex", {
      method: "POST",
      body: JSON.stringify(params),
    })
  },

  // Get indexing status (not available in v2)
  async getIndexingStatus(): Promise<never> {
    throw new Error("Not available in v2")
  },

  // File operations (not available in v2 — v2 uses document-based model, not filesystem)
  async createFolder(_folderPath: string): Promise<never> {
    throw new Error("Not available in v2")
  },

  async createFile(_path: string, _content?: string): Promise<never> {
    throw new Error("Not available in v2")
  },

  async saveFile(_path: string, _content: string): Promise<never> {
    throw new Error("Not available in v2")
  },

  async deleteItem(_path: string): Promise<never> {
    throw new Error("Not available in v2")
  },

  async renameItem(_oldPath: string, _newPath: string): Promise<never> {
    throw new Error("Not available in v2")
  },

  async uploadFile(_file: File, _path?: string): Promise<never> {
    throw new Error("Not available in v2")
  },

  // Chat sessions
  async getChatSessions(
    targetType: "rag" | "ide" | "notes",
    targetId: string
  ): Promise<{ status: string; sessions: ChatSessionSummary[] }> {
    return fetchAPI(
      `/api/chat/sessions?target_type=${targetType}&target_id=${encodeURIComponent(targetId)}`
    )
  },

  async getChatSession(
    sessionId: string,
    _targetType: "rag" | "ide" | "notes",
    _targetId: string
  ): Promise<{ status: string; session: ChatSession }> {
    return fetchAPI(`/api/chat/sessions/${sessionId}`)
  },

  async saveChatSession(session: ChatSession): Promise<{ status: string; session: ChatSession }> {
    return fetchAPI("/api/chat/sessions", {
      method: "POST",
      body: JSON.stringify({
        target_type: session.target_type,
        target_id: session.target_id,
        title: session.title,
      }),
    })
  },

  async deleteChatSession(
    sessionId: string,
    _targetType: "rag" | "ide" | "notes",
    _targetId: string
  ): Promise<{ status: string }> {
    return fetchAPI(`/api/chat/sessions/${sessionId}`, { method: "DELETE" })
  },
}
