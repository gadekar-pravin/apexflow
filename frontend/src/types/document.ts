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
  chunk_count?: number
  ingestion_version?: number
  created_at: string
  updated_at?: string
}

export interface DocumentsResponse {
  documents: V2Document[]
}

export interface SearchResult {
  chunk_text: string
  document_id: string
  filename: string
  rrf_score: number
  vector_score: number
  text_score: number
}

export interface SearchResponse {
  status: string
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

export interface IndexingStatus {
  active: boolean
  total: number
  completed: number
  currentFile: string
}
