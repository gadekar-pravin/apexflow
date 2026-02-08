// Document types matching backend routers/rag.py and routers/chat.py

// v1 tree item type (kept for reference, no longer used by API)
export interface DocumentTreeItem {
  name: string
  path: string
  type: "folder" | string // file extension
  size?: number
  indexed?: boolean
  status?: "complete" | "unindexed" | "error"
  hash?: string
  chunk_count?: number
  error?: string
  children?: DocumentTreeItem[]
}

// v2 document type (flat list, not a tree)
export interface V2Document {
  id: string
  filename: string
  file_hash: string
  total_chunks: number
  ingestion_version?: number
  indexed_at: string
  updated_at?: string
  doc_type?: string
  embedding_model?: string
}

export interface DocumentsResponse {
  documents: V2Document[]
}

export interface SearchResult {
  chunk_id: string
  document_id: string
  content: string
  chunk_index: number
  rrf_score: number
  vector_score: number
  text_score: number
}

export interface SearchResponse {
  results: SearchResult[]
}

export interface ChatMessage {
  id: string
  role: "user" | "assistant" | "system"
  content: string
  timestamp: number
  images?: string[]
  contexts?: string[]
  fileContexts?: FileContext[]
}

export interface FileContext {
  path: string
  content?: string
}

export interface ChatSession {
  id: string
  target_type: "rag" | "ide" | "notes"
  target_id: string
  title: string
  messages: ChatMessage[]
  created_at: number
  updated_at: number
  model?: string
  system_prompt?: string
  tools?: Record<string, unknown>[]
}

export interface ChatSessionSummary {
  id: string
  title: string
  created_at: number
  updated_at: number
  model?: string
  preview: string
}

export interface ReindexResult {
  doc_id: string
  status: string
  total_chunks: number
}

export interface ReindexResponse {
  reindexed: ReindexResult[]
}

export interface IndexingStatus {
  active: boolean
  total: number
  completed: number
  currentFile: string
}
