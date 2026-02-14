import { useState, useCallback, useRef, useEffect, useMemo } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { ChevronRight } from "lucide-react"
import { ResizablePanel } from "@/components/ui/resizable-panel"
import {
  WelcomeScreen,
  ChatMessageList,
  ChatInput,
  ChatSessionList,
} from "@/components/chat"
import { chatService } from "@/services/chatService"
import { runsService } from "@/services/runsService"
import { useAuth } from "@/contexts/AuthContext"
import { useReasoningEvents } from "@/hooks/useReasoningEvents"
import { parseMetadata, stepsFromGraphNodes, type ConsolidatedStep } from "@/components/chat/reasoning-shared"
import type { AgentChatMessage, VisualizationSpec } from "@/types"

const MAX_POLL_ERRORS = 15
const MAX_VIZ_PER_MESSAGE = 5
const MAX_ROWS_PER_CHART = 50

function isValidVizSpec(spec: unknown): spec is VisualizationSpec {
  if (!spec || typeof spec !== "object") return false
  const s = spec as Record<string, unknown>
  return (
    s.schema_version === 1 &&
    typeof s.id === "string" &&
    typeof s.title === "string" &&
    typeof s.chart_type === "string" &&
    ["bar", "line", "pie", "area"].includes(s.chart_type as string) &&
    Array.isArray(s.data) &&
    s.data.length > 0 &&
    typeof s.x_key === "string" &&
    Array.isArray(s.y_keys) &&
    s.y_keys.length > 0 &&
    // Validate first data row is a non-null object before using `in`
    typeof (s.data as unknown[])[0] === "object" &&
    (s.data as unknown[])[0] !== null &&
    // Validate keys exist in data
    s.x_key in (s.data as Record<string, unknown>[])[0] &&
    (s.y_keys as string[]).every((k) => k in (s.data as Record<string, unknown>[])[0])
  )
}

function sanitizeVisualizations(rawViz: unknown): VisualizationSpec[] | null {
  if (!Array.isArray(rawViz) || rawViz.length === 0) return null
  const valid = rawViz
    .filter(isValidVizSpec)
    .slice(0, MAX_VIZ_PER_MESSAGE)
    .map((spec) => ({
      ...spec,
      data: spec.data.slice(0, MAX_ROWS_PER_CHART),
    }))
  return valid.length > 0 ? valid : null
}

export function ChatPage() {
  const auth = useAuth()
  const canFetchData = !auth.isConfigured || auth.isAuthenticated
  const queryClient = useQueryClient()
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<AgentChatMessage[]>([])
  const [inputValue, setInputValue] = useState("")
  const [isRunning, setIsRunning] = useState(false)
  const [activeRunId, setActiveRunId] = useState<string | null>(null)
  const [expandedReasoningIds, setExpandedReasoningIds] = useState<Set<string>>(new Set())
  const activePollsRef = useRef<Set<ReturnType<typeof setTimeout>>>(new Set())
  const currentSessionIdRef = useRef<string | null>(null)
  const unmountedRef = useRef(false)
  const skipNextLoadRef = useRef(false)

  // Centralized SSE reasoning events
  const { stepsMap: liveStepsMap } = useReasoningEvents(activeRunId, currentSessionId)

  // Persisted reasoning steps reconstructed from graph data
  const [persistedStepsMap, setPersistedStepsMap] = useState<Map<string, ConsolidatedStep[]>>(new Map())
  const fetchedRunIdsRef = useRef<Set<string>>(new Set())

  // Clear persisted state on session change
  useEffect(() => {
    setPersistedStepsMap(new Map())
    fetchedRunIdsRef.current = new Set()
  }, [currentSessionId])

  // Fetch graph data for run_ids found in messages
  useEffect(() => {
    if (messages.length === 0) return

    const runIdsToFetch: string[] = []
    for (const msg of messages) {
      if (msg.role !== "assistant") continue
      const meta = parseMetadata(msg.metadata)
      const runId = meta?.run_id as string | undefined
      if (
        runId &&
        !fetchedRunIdsRef.current.has(runId) &&
        !liveStepsMap.has(runId)
      ) {
        runIdsToFetch.push(runId)
      }
    }

    if (runIdsToFetch.length === 0) return

    // Mark as in-flight to prevent duplicate concurrent requests
    for (const id of runIdsToFetch) fetchedRunIdsRef.current.add(id)

    Promise.allSettled(
      runIdsToFetch.map((id) => runsService.get(id).then((run) => ({ id, run })))
    ).then((results) => {
      const newEntries: [string, ConsolidatedStep[]][] = []
      for (let i = 0; i < results.length; i++) {
        const result = results[i]
        if (result.status === "fulfilled") {
          const { id, run } = result.value
          if (run.graph?.nodes?.length) {
            const steps = stepsFromGraphNodes(run.graph.nodes)
            if (steps.length > 0) newEntries.push([id, steps])
          }
        } else {
          // Remove failed IDs so the effect can retry on next trigger
          fetchedRunIdsRef.current.delete(runIdsToFetch[i])
        }
      }
      if (newEntries.length > 0) {
        setPersistedStepsMap((prev) => {
          const next = new Map(prev)
          for (const [id, steps] of newEntries) next.set(id, steps)
          return next
        })
      }
    })
  }, [messages, liveStepsMap])

  // Merge persisted + live steps (live always wins)
  const stepsMap = useMemo(() => {
    const merged = new Map(persistedStepsMap)
    for (const [id, steps] of liveStepsMap) merged.set(id, steps)
    return merged
  }, [persistedStepsMap, liveStepsMap])

  const handleToggleReasoning = useCallback((messageId: string) => {
    setExpandedReasoningIds((prev) => {
      const next = new Set(prev)
      if (next.has(messageId)) {
        next.delete(messageId)
      } else {
        next.add(messageId)
      }
      return next
    })
  }, [])

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
              let visualizations: VisualizationSpec[] | null = null

              if (run.status === "completed" && run.graph?.nodes) {
                const completedNodes = run.graph.nodes
                  .filter((n) => n.data.status === "completed" && n.data.output)

                // Extract text from FormatterAgent (or last completed node as fallback)
                const formatterNode = completedNodes.find(
                  (n) => n.data.type === "FormatterAgent"
                )
                const textSource = formatterNode || completedNodes[completedNodes.length - 1]
                if (textSource?.data.output) {
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  let raw: any = textSource.data.output
                  if (typeof raw === "string") {
                    try { raw = JSON.parse(raw) } catch { /* keep as string */ }
                  }
                  if (typeof raw === "string") {
                    outputText = raw
                  } else if (raw && typeof raw === "object") {
                    outputText = raw.markdown_report || raw.result || raw.output || JSON.stringify(raw, null, 2)
                  }
                }

                // Extract charts from ChartAgent; fall back to FormatterAgent for old runs
                const chartNode = completedNodes.find(
                  (n) => n.data.type === "ChartAgent"
                )
                const vizSource = chartNode || formatterNode
                if (vizSource?.data.output) {
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  let vizRaw: any = vizSource.data.output
                  if (typeof vizRaw === "string") {
                    try { vizRaw = JSON.parse(vizRaw) } catch { /* keep as string */ }
                  }
                  if (vizRaw && typeof vizRaw === "object") {
                    visualizations = sanitizeVisualizations(vizRaw.visualizations)
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

              // Build metadata — always include run_id for reasoning trace lookup
              const metadata: Record<string, unknown> = { run_id: runId }
              if (visualizations) {
                metadata.visualizations_schema_version = 1
                metadata.visualizations = visualizations
              }

              // Always persist the assistant message to DB so it's
              // available when the user navigates back to this session.
              const onOriginalSession = currentSessionIdRef.current === sessionId
              try {
                const assistantMsg = await chatService.addMessage(
                  sessionId,
                  "assistant",
                  outputText,
                  metadata
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
                    metadata: metadata,
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
        className="border-r border-border/50 bg-sidebar/70"
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
        <div className="flex items-center justify-between border-b border-border/50 bg-card/70 backdrop-blur-xs px-6 h-14 shrink-0">
          <div className="flex items-center gap-1.5 text-sm min-w-0">
            <button
              type="button"
              className="text-muted-foreground hover:text-primary cursor-pointer transition-colors shrink-0 bg-transparent border-none p-0 text-sm"
              onClick={handleCreateSession}
            >
              Home
            </button>
            <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/60 shrink-0" />
            <span className="font-medium text-foreground truncate">
              {currentSessionId
                ? sessions.find((s) => s.id === currentSessionId)?.title || "Chat"
                : "New Chat"}
            </span>
          </div>
        </div>

        {/* Messages with fixed footer input, or Welcome with inline input */}
        {hasMessages ? (
          <>
            <ChatMessageList
              messages={messages}
              isRunning={isRunning}
              stepsMap={stepsMap}
              activeRunId={activeRunId}
              expandedReasoningIds={expandedReasoningIds}
              onToggleReasoning={handleToggleReasoning}
            />
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
    </div>
  )
}
