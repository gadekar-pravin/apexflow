import { useState, useEffect, useCallback, useRef } from "react"
import { getAPIUrl } from "../services/api"
import { useSmartInterval } from "./useSmartInterval"

export type ConnectionState = "connected" | "connecting" | "disconnected"

interface UseApiHealthResult {
  state: ConnectionState
  isConnected: boolean
  isConnecting: boolean
  lastError: Error | null
  checkNow: () => void
}

export function useApiHealth(): UseApiHealthResult {
  const [state, setState] = useState<ConnectionState>("connecting")
  const [lastError, setLastError] = useState<Error | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)

  const checkHealth = useCallback(async () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }

    abortControllerRef.current = new AbortController()

    try {
      const response = await fetch(getAPIUrl("/liveness"), {
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
        return
      }
      setState("disconnected")
      setLastError(error instanceof Error ? error : new Error("Unknown error"))
    }
  }, [])

  useSmartInterval({ callback: checkHealth, intervalMs: 60_000 })

  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }
    }
  }, [])

  return {
    state,
    isConnected: state === "connected",
    isConnecting: state === "connecting",
    lastError,
    checkNow: checkHealth,
  }
}
