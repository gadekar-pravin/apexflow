// Settings types matching backend config/settings.json

export interface Settings {
  models: ModelSettings
  rag: RagSettings
  agent: AgentSettings
  testing: TestingSettings
  remme: RemmeSettings
  gemini: GeminiSettings
  news: NewsSettings
}

export interface ModelSettings {
  embedding: string
  semantic_chunking: string
  image_captioning: string
  memory_extraction: string
  insights_provider: string
}

export interface RagSettings {
  chunk_size: number
  chunk_overlap: number
  max_chunk_length: number
  semantic_word_limit: number
  top_k: number
}

export interface AgentSettings {
  model_provider: string
  default_model: string
  overrides: Record<string, string>
  max_steps: number
  max_lifelines_per_step: number
  planning_mode: "conservative" | "aggressive"
  rate_limit_interval: number
  max_cost_per_run: number
  warn_at_cost: number
}

export interface TestingSettings {
  feedback_mode: "with_permission" | "auto" | "disabled"
  regenerate_on_type_changes: boolean
  regenerate_on_docstring_changes: boolean
  test_agent_model: string
}

export interface RemmeSettings {
  extraction_prompt: string
}

export interface GeminiSettings {
  api_key_env: string
}

export interface NewsSettings {
  sources: NewsSource[]
}

export interface NewsSource {
  id: string
  name: string
  url: string
  type: "api" | "rss"
  feed_url?: string
  enabled: boolean
}
