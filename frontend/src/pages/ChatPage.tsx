import { useState, useCallback, useRef, useEffect } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { PanelRightOpen, PanelRightClose } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  WelcomeScreen,
  ChatMessageList,
  ChatInput,
  ReasoningSidebar,
  ChatSessionList,
} from "@/components/chat"
import { chatService } from "@/services/chatService"
import { runsService } from "@/services/runsService"
import type { AgentChatMessage } from "@/types"

export function ChatPage() {
  const queryClient = useQueryClient()
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<AgentChatMessage[]>([])
  const [inputValue, setInputValue] = useState("")
  const [isRunning, setIsRunning] = useState(false)
  const [activeRunId, setActiveRunId] = useState<string | null>(null)
  const [showReasoning, setShowReasoning] = useState(false)
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null)

  // Fetch chat sessions
  const { data: sessions = [] } = useQuery({
    queryKey: ["chatSessions"],
    queryFn: chatService.listSessions,
  })

  // Load messages when session changes
  useEffect(() => {
    if (!currentSessionId) {
      setMessages([])
      return
    }
    chatService.getSession(currentSessionId).then(({ messages: msgs }) => {
      setMessages(msgs)
    }).catch(() => {
      setMessages([])
    })
  }, [currentSessionId])

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current)
      }
    }
  }, [])

  const pollRunStatus = useCallback(
    (runId: string, sessionId: string) => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current)
      }

      pollIntervalRef.current = setInterval(async () => {
        try {
          const run = await runsService.get(runId)
          if (run.status === "completed" || run.status === "failed") {
            if (pollIntervalRef.current) {
              clearInterval(pollIntervalRef.current)
              pollIntervalRef.current = null
            }

            // Extract output from run graph
            let outputText = ""
            if (run.status === "completed" && run.graph?.nodes) {
              // Find the last completed node's output
              const completedNodes = run.graph.nodes
                .filter((n) => n.data.status === "completed" && n.data.output)
                .sort((a, b) => {
                  // Prefer FormatterAgent if available, otherwise take the last one
                  if (a.data.type === "FormatterAgent") return 1
                  if (b.data.type === "FormatterAgent") return -1
                  return 0
                })
              const lastNode = completedNodes[completedNodes.length - 1]
              if (lastNode?.data.output) {
                const raw = lastNode.data.output
                outputText = typeof raw === "string" ? raw : JSON.stringify(raw, null, 2)
              }
            }

            if (run.status === "failed") {
              const failedNode = run.graph?.nodes?.find(
                (n) => n.data.status === "failed"
              )
              outputText = failedNode?.data.error || "The agent run failed."
            }

            if (!outputText) {
              outputText = run.status === "completed"
                ? "Task completed successfully."
                : "Something went wrong."
            }

            // Store assistant message
            try {
              const assistantMsg = await chatService.addMessage(
                sessionId,
                "assistant",
                outputText
              )
              setMessages((prev) => [...prev, assistantMsg])
            } catch {
              // Still show it locally even if DB save fails
              const localMsg: AgentChatMessage = {
                id: `local-${Date.now()}`,
                session_id: sessionId,
                role: "assistant",
                content: outputText,
                metadata: null,
                created_at: new Date().toISOString(),
              }
              setMessages((prev) => [...prev, localMsg])
            }

            setIsRunning(false)
            setActiveRunId(null)
          }
        } catch {
          // Poll error — keep trying
        }
      }, 2000)
    },
    []
  )

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim()
      if (!trimmed || isRunning) return

      try {
        // 1. Ensure a session exists
        let sessionId = currentSessionId
        if (!sessionId) {
          const title = trimmed.slice(0, 50) + (trimmed.length > 50 ? "..." : "")
          const session = await chatService.createSession(title)
          sessionId = session.id
          setCurrentSessionId(sessionId)
          queryClient.invalidateQueries({ queryKey: ["chatSessions"] })
        }

        // 2. Store + display user message
        const userMsg = await chatService.addMessage(sessionId, "user", trimmed)
        setMessages((prev) => [...prev, userMsg])
        setInputValue("")

        // 3. Trigger agent run
        setIsRunning(true)
        const run = await runsService.create({ query: trimmed })
        setActiveRunId(run.id)

        // 4. Poll for completion
        pollRunStatus(run.id, sessionId)
      } catch (err) {
        console.error("Failed to send message:", err)
        setIsRunning(false)
      }
    },
    [currentSessionId, isRunning, pollRunStatus, queryClient]
  )

  const handleCreateSession = useCallback(() => {
    setCurrentSessionId(null)
    setMessages([])
    setInputValue("")
    setActiveRunId(null)
    setIsRunning(false)
  }, [])

  const handleDeleteSession = useCallback(
    async (id: string) => {
      try {
        await chatService.deleteSession(id)
        queryClient.invalidateQueries({ queryKey: ["chatSessions"] })
        if (currentSessionId === id) {
          handleCreateSession()
        }
      } catch (err) {
        console.error("Failed to delete session:", err)
      }
    },
    [currentSessionId, handleCreateSession, queryClient]
  )

  const handleSelectSession = useCallback((id: string) => {
    setCurrentSessionId(id)
    setActiveRunId(null)
    setIsRunning(false)
  }, [])

  const handleSend = useCallback(() => {
    sendMessage(inputValue)
  }, [inputValue, sendMessage])

  const hasMessages = messages.length > 0

  return (
    <div className="flex h-full">
      {/* Session sidebar */}
      <div className="w-56 border-r border-border/40 bg-sidebar/40 flex-shrink-0">
        <ChatSessionList
          sessions={sessions}
          currentSessionId={currentSessionId}
          onSelect={handleSelectSession}
          onCreate={handleCreateSession}
          onDelete={handleDeleteSession}
        />
      </div>

      {/* Main chat area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border/40 px-6 h-14 shrink-0">
          <h1 className="text-sm font-medium text-foreground truncate">
            {currentSessionId
              ? sessions.find((s) => s.id === currentSessionId)?.title || "Chat"
              : "New Chat"}
          </h1>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowReasoning(!showReasoning)}
            className="text-muted-foreground"
          >
            {showReasoning ? (
              <PanelRightClose className="h-4 w-4 mr-1.5" />
            ) : (
              <PanelRightOpen className="h-4 w-4 mr-1.5" />
            )}
            <span className="text-xs">Reasoning</span>
          </Button>
        </div>

        {/* Messages or Welcome */}
        {hasMessages ? (
          <ChatMessageList messages={messages} isRunning={isRunning} />
        ) : (
          <WelcomeScreen onSend={sendMessage} />
        )}

        {/* Input */}
        <ChatInput
          value={inputValue}
          onChange={setInputValue}
          onSend={handleSend}
          disabled={isRunning}
        />
      </div>

      {/* Reasoning sidebar */}
      {showReasoning && (
        <div className="w-80 border-l border-border/40 bg-sidebar/40 flex-shrink-0">
          <ReasoningSidebar activeRunId={activeRunId} />
        </div>
      )}
    </div>
  )
}
