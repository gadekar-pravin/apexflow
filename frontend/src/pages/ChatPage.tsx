import { useState, useCallback, useRef, useEffect } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { PanelRightOpen, PanelRightClose } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ResizablePanel } from "@/components/ui/resizable-panel"
import {
  WelcomeScreen,
  ChatMessageList,
  ChatInput,
  ReasoningSidebar,
  ChatSessionList,
} from "@/components/chat"
import { chatService } from "@/services/chatService"
import { runsService } from "@/services/runsService"
import { useAuth } from "@/contexts/AuthContext"
import type { AgentChatMessage } from "@/types"

const MAX_POLL_ERRORS = 15

export function ChatPage() {
  const auth = useAuth()
  const canFetchData = !auth.isConfigured || auth.isAuthenticated
  const queryClient = useQueryClient()
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<AgentChatMessage[]>([])
  const [inputValue, setInputValue] = useState("")
  const [isRunning, setIsRunning] = useState(false)
  const [activeRunId, setActiveRunId] = useState<string | null>(null)
  const [showReasoning, setShowReasoning] = useState(false)
  const activePollsRef = useRef<Set<ReturnType<typeof setTimeout>>>(new Set())
  const currentSessionIdRef = useRef<string | null>(null)
  const unmountedRef = useRef(false)
  const skipNextLoadRef = useRef(false)

  // Keep ref in sync with state for use in async callbacks
  useEffect(() => {
    currentSessionIdRef.current = currentSessionId
  }, [currentSessionId])

  // Fetch chat sessions
  const { data: sessions = [] } = useQuery({
    queryKey: ["chatSessions"],
    queryFn: chatService.listSessions,
    enabled: canFetchData,
  })

  // Load messages when session changes
  useEffect(() => {
    if (!currentSessionId) {
      setMessages([])
      return
    }
    if (!canFetchData) return

    // Skip loading when sendMessage just created this session —
    // messages are managed locally and the server may not have them yet.
    if (skipNextLoadRef.current) {
      skipNextLoadRef.current = false
      return
    }

    let cancelled = false
    chatService.getSession(currentSessionId).then(({ messages: msgs }) => {
      if (!cancelled) setMessages(msgs)
    }).catch(() => {
      if (!cancelled) setMessages([])
    })
    return () => { cancelled = true }
  }, [currentSessionId, canFetchData])

  // Cleanup all active polls on unmount
  useEffect(() => {
    return () => {
      unmountedRef.current = true
      activePollsRef.current.forEach((id) => clearTimeout(id))
      activePollsRef.current.clear()
    }
  }, [])

  // Each call creates an independent poll loop so overlapping runs
  // across sessions can all persist their results without cancelling
  // each other.  Timeouts are tracked in activePollsRef for cleanup.
  const pollRunStatus = useCallback(
    (runId: string, sessionId: string) => {
      let errorCount = 0

      const scheduleTick = () => {
        const id = setTimeout(async () => {
          activePollsRef.current.delete(id)

          if (unmountedRef.current) return

          try {
            const run = await runsService.get(runId)
            errorCount = 0

            if (run.status === "completed" || run.status === "failed") {
              // Extract output from run graph
              let outputText = ""
              if (run.status === "completed" && run.graph?.nodes) {
                const completedNodes = run.graph.nodes
                  .filter((n) => n.data.status === "completed" && n.data.output)
                  .sort((a, b) => {
                    if (a.data.type === "FormatterAgent") return 1
                    if (b.data.type === "FormatterAgent") return -1
                    return 0
                  })
                const lastNode = completedNodes[completedNodes.length - 1]
                if (lastNode?.data.output) {
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  let raw: any = lastNode.data.output
                  if (typeof raw === "string") {
                    try { raw = JSON.parse(raw) } catch { /* keep as string */ }
                  }
                  if (typeof raw === "string") {
                    outputText = raw
                  } else if (raw && typeof raw === "object") {
                    outputText = raw.markdown_report || raw.result || raw.output || JSON.stringify(raw, null, 2)
                  }
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

              // Always persist the assistant message to DB so it's
              // available when the user navigates back to this session.
              const onOriginalSession = currentSessionIdRef.current === sessionId
              try {
                const assistantMsg = await chatService.addMessage(
                  sessionId,
                  "assistant",
                  outputText
                )
                if (onOriginalSession) {
                  setMessages((prev) => [...prev, assistantMsg])
                }
              } catch {
                if (onOriginalSession) {
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
              }

              if (onOriginalSession) {
                setIsRunning(false)
                setActiveRunId(null)
              }
              return
            }
          } catch {
            errorCount++
            if (errorCount >= MAX_POLL_ERRORS) {
              if (currentSessionIdRef.current === sessionId) {
                setIsRunning(false)
                setActiveRunId(null)
              }
              return
            }
          }

          if (!unmountedRef.current) scheduleTick()
        }, 2000)
        activePollsRef.current.add(id)
      }

      scheduleTick()
    },
    []
  )

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim()
      if (!trimmed || isRunning || !canFetchData) return

      try {
        // 1. Ensure a session exists
        let sessionId = currentSessionId
        if (!sessionId) {
          const title = trimmed.slice(0, 50) + (trimmed.length > 50 ? "..." : "")
          const session = await chatService.createSession(title)
          sessionId = session.id
          skipNextLoadRef.current = true
          setCurrentSessionId(sessionId)
          queryClient.invalidateQueries({ queryKey: ["chatSessions"] })
        }

        // 2. Store + display user message (with local fallback)
        let userMsg: AgentChatMessage
        try {
          userMsg = await chatService.addMessage(sessionId, "user", trimmed)
        } catch {
          userMsg = {
            id: `local-${Date.now()}`,
            session_id: sessionId,
            role: "user",
            content: trimmed,
            metadata: null,
            created_at: new Date().toISOString(),
          }
        }
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
    [currentSessionId, isRunning, canFetchData, pollRunStatus, queryClient]
  )

  const handleCreateSession = useCallback(() => {
    // Don't cancel polling — let any background run persist its result
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
    // Don't cancel polling — let any background run persist its result
    setCurrentSessionId(id)
    setActiveRunId(null)
    setIsRunning(false)
  }, [])

  const handleSend = useCallback(() => {
    sendMessage(inputValue)
  }, [inputValue, sendMessage])

  if (auth.isConfigured && !auth.isAuthenticated) {
    return null
  }

  const hasMessages = messages.length > 0

  return (
    <div className="flex h-full">
      {/* Session sidebar */}
      <ResizablePanel
        defaultWidth={224}
        minWidth={180}
        maxWidth={400}
        storageKey="apexflow.chat.sessionsWidth"
        className="border-r border-border/40 bg-sidebar/40"
      >
        <ChatSessionList
          sessions={sessions}
          currentSessionId={currentSessionId}
          onSelect={handleSelectSession}
          onCreate={handleCreateSession}
          onDelete={handleDeleteSession}
        />
      </ResizablePanel>

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

        {/* Messages with fixed footer input, or Welcome with inline input */}
        {hasMessages ? (
          <>
            <ChatMessageList messages={messages} isRunning={isRunning} />
            <ChatInput
              value={inputValue}
              onChange={setInputValue}
              onSend={handleSend}
              disabled={isRunning}
              placeholder="Ask a follow-up question..."
            />
          </>
        ) : (
          <WelcomeScreen
            onSend={sendMessage}
            inputValue={inputValue}
            onInputChange={setInputValue}
            onInputSend={handleSend}
            disabled={isRunning}
          />
        )}
      </div>

      {/* Reasoning sidebar — always mounted to preserve events across toggle */}
      {showReasoning && (
        <ResizablePanel
          defaultWidth={320}
          minWidth={240}
          maxWidth={600}
          storageKey="apexflow.chat.reasoningWidth"
          side="left"
          className="border-l border-border/40 bg-sidebar/40"
        >
          <ReasoningSidebar activeRunId={activeRunId} sessionId={currentSessionId} />
        </ResizablePanel>
      )}
    </div>
  )
}
