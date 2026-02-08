import { createContext, useContext, useEffect, useRef, useState, useCallback, type ReactNode } from "react"
import type { SSEEvent } from "@/types"
import { getSSEUrl, getAuthToken } from "../services/api"

export type SSEConnectionState = "connected" | "connecting" | "disconnected"

interface SSEContextValue {
  connectionState: SSEConnectionState
  isConnected: boolean
  isConnecting: boolean
  lastError: Event | null
  subscribe: (callback: (event: SSEEvent) => void) => () => void
}

const SSEContext = createContext<SSEContextValue | null>(null)

export function SSEProvider({ children }: { children: ReactNode }) {
  const [connectionState, setConnectionState] = useState<SSEConnectionState>("disconnected")
  const [lastError, setLastError] = useState<Event | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const subscribersRef = useRef<Set<(event: SSEEvent) => void>>(new Set())
  const mountedRef = useRef(true)

  const connect = useCallback(() => {
    if (!mountedRef.current) return

    setConnectionState("connecting")
    setLastError(null)

    if (eventSourceRef.current) {
      eventSourceRef.current.close()
    }

    // EventSource doesn't support custom headers, so pass token as query param
    void getAuthToken().then((token) => {
      if (!mountedRef.current) return

      let url = getSSEUrl("/api/events")
      if (token) {
        url += `?token=${encodeURIComponent(token)}`
      }

      const eventSource = new EventSource(url)
      eventSourceRef.current = eventSource

      eventSource.onopen = () => {
        if (!mountedRef.current) return
        setConnectionState("connected")
      }

      eventSource.onmessage = (event) => {
        if (!mountedRef.current) return
        try {
          const data = JSON.parse(event.data) as SSEEvent
          subscribersRef.current.forEach((callback) => callback(data))
        } catch (error) {
          console.error("Failed to parse SSE event:", error)
        }
      }

      eventSource.onerror = (error) => {
        if (!mountedRef.current) return
        console.error("SSE error:", error)
        setConnectionState("disconnected")
        setLastError(error)

        eventSource.close()
        reconnectTimeoutRef.current = setTimeout(() => {
          if (mountedRef.current) {
            connect()
          }
        }, 5000)
      }
    })
  }, [])

  useEffect(() => {
    mountedRef.current = true
    connect()

    return () => {
      mountedRef.current = false
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
        eventSourceRef.current = null
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
        reconnectTimeoutRef.current = null
      }
    }
  }, [connect])

  const subscribe = useCallback((callback: (event: SSEEvent) => void) => {
    subscribersRef.current.add(callback)
    return () => {
      subscribersRef.current.delete(callback)
    }
  }, [])

  const value: SSEContextValue = {
    connectionState,
    isConnected: connectionState === "connected",
    isConnecting: connectionState === "connecting",
    lastError,
    subscribe,
  }

  return <SSEContext.Provider value={value}>{children}</SSEContext.Provider>
}

export function useSSEContext() {
  const context = useContext(SSEContext)
  if (!context) {
    throw new Error("useSSEContext must be used within an SSEProvider")
  }
  return context
}

/**
 * Hook to subscribe to SSE events using the shared connection
 */
export function useSSESubscription(onEvent?: (event: SSEEvent) => void) {
  const { subscribe, connectionState, isConnected, isConnecting, lastError } = useSSEContext()

  useEffect(() => {
    if (!onEvent) return
    return subscribe(onEvent)
  }, [subscribe, onEvent])

  return { connectionState, isConnected, isConnecting, lastError }
}
