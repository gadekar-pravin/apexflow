import { fetchAPI } from "./api"
import type { AgentChatSession, AgentChatMessage } from "@/types"

interface SessionsResponse {
  status: string
  sessions: AgentChatSession[]
}

interface SessionDetailResponse {
  status: string
  session: AgentChatSession
  messages: AgentChatMessage[]
}

interface CreateSessionResponse {
  status: string
  session: AgentChatSession
}

interface MessageResponse {
  status: string
  message: AgentChatMessage
}

interface MessagesResponse {
  status: string
  messages: AgentChatMessage[]
}

export const chatService = {
  async listSessions(): Promise<AgentChatSession[]> {
    const res = await fetchAPI<SessionsResponse>("/api/chat/sessions?target_type=chat&target_id=chat")
    return res.sessions
  },

  async getSession(sessionId: string): Promise<{ session: AgentChatSession; messages: AgentChatMessage[] }> {
    const res = await fetchAPI<SessionDetailResponse>(`/api/chat/sessions/${sessionId}`)
    return { session: res.session, messages: res.messages }
  },

  async createSession(title: string): Promise<AgentChatSession> {
    const res = await fetchAPI<CreateSessionResponse>("/api/chat/sessions", {
      method: "POST",
      body: JSON.stringify({
        target_type: "chat",
        target_id: "chat",
        title,
      }),
    })
    return res.session
  },

  async deleteSession(sessionId: string): Promise<void> {
    await fetchAPI<{ status: string }>(`/api/chat/sessions/${sessionId}`, {
      method: "DELETE",
    })
  },

  async addMessage(
    sessionId: string,
    role: "user" | "assistant",
    content: string
  ): Promise<AgentChatMessage> {
    const res = await fetchAPI<MessageResponse>(
      `/api/chat/sessions/${sessionId}/messages`,
      {
        method: "POST",
        body: JSON.stringify({ role, content }),
      }
    )
    return res.message
  },

  async getMessages(sessionId: string, limit = 100): Promise<AgentChatMessage[]> {
    const res = await fetchAPI<MessagesResponse>(
      `/api/chat/sessions/${sessionId}/messages?limit=${limit}`
    )
    return res.messages
  },
}
