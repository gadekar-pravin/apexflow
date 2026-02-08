import { useState, useEffect, useCallback, useRef } from "react"

export type ConnectionState = "connected" | "connecting" | "disconnected"

interface UseApiHealthResult {
  state: ConnectionState
  isConnected: boolean
  isConnecting: boolean
  lastError: Error | null
  checkNow: () => void
}

const HEALTH_CHECK_INTERVAL = 30000 // 30 seconds

export function useApiHealth(): UseApiHealthResult {
  const [state, setState] = useState<ConnectionState>("connecting")
  const [lastError, setLastError] = useState<Error | null>(null)
  const intervalRef = useRef<NodeJS.Timeout | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)

  const checkHealth = useCallback(async () => {
    // Cancel any pending request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }

    abortControllerRef.current = new AbortController()

    try {
      const response = await fetch("/liveness", {
        method: "GET",
        signal: abortControllerRef.current.signal,
      })

      if (response.ok) {
        setState("connected")
        setLastError(null)
      } else {
        setState("disconnected")
        setLastError(new Error(`Health check failed: ${response.status}`))
      }
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") {
        return // Ignore aborted requests
      }
      setState("disconnected")
      setLastError(error instanceof Error ? error : new Error("Unknown error"))
    }
  }, [])

  // Initial check and interval setup
  useEffect(() => {
    checkHealth()

    intervalRef.current = setInterval(checkHealth, HEALTH_CHECK_INTERVAL)

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
      }
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }
    }
  }, [checkHealth])

  return {
    state,
    isConnected: state === "connected",
    isConnecting: state === "connecting",
    lastError,
    checkNow: checkHealth,
  }
}
