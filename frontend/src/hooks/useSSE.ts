import { useEffect, useRef, useCallback, useState } from "react"
import { API_URL } from "@/services/api"
import type { SSEEvent } from "@/types"

export type SSEConnectionState = "connected" | "connecting" | "disconnected"

interface UseSSEOptions {
  onEvent?: (event: SSEEvent) => void
  onError?: (error: Event) => void
  onOpen?: () => void
  enabled?: boolean
}

interface UseSSEResult {
  disconnect: () => void
  reconnect: () => void
  connectionState: SSEConnectionState
  isConnected: boolean
  isConnecting: boolean
  lastError: Event | null
}

/**
 * @deprecated Prefer using useSSESubscription from SSEContext for shared connection
 */
export function useSSE(options: UseSSEOptions = {}): UseSSEResult {
  const { onEvent, onError, onOpen, enabled = true } = options
  const eventSourceRef = useRef<EventSource | null>(null)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const mountedRef = useRef(true)
  const [connectionState, setConnectionState] = useState<SSEConnectionState>("disconnected")
  const [lastError, setLastError] = useState<Event | null>(null)

  const connect = useCallback(() => {
    if (!enabled || !mountedRef.current) return

    setConnectionState("connecting")
    setLastError(null)

    // Clean up existing connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
    }

    const eventSource = new EventSource(`${API_URL}/events`)
    eventSourceRef.current = eventSource

    eventSource.onopen = () => {
      if (!mountedRef.current) return
      console.log("SSE connected")
      setConnectionState("connected")
      onOpen?.()
    }

    eventSource.onmessage = (event) => {
      if (!mountedRef.current) return
      try {
        const data = JSON.parse(event.data) as SSEEvent
        onEvent?.(data)
      } catch (error) {
        console.error("Failed to parse SSE event:", error)
      }
    }

    eventSource.onerror = (error) => {
      if (!mountedRef.current) return
      console.error("SSE error:", error)
      setConnectionState("disconnected")
      setLastError(error)
      onError?.(error)

      // Reconnect after 5 seconds
      eventSource.close()
      reconnectTimeoutRef.current = setTimeout(() => {
        if (mountedRef.current) {
          connect()
        }
      }, 5000)
    }
  }, [enabled, onEvent, onError, onOpen])

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

  const disconnect = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }
    if (mountedRef.current) {
      setConnectionState("disconnected")
    }
  }, [])

  return {
    disconnect,
    reconnect: connect,
    connectionState,
    isConnected: connectionState === "connected",
    isConnecting: connectionState === "connecting",
    lastError,
  }
}
