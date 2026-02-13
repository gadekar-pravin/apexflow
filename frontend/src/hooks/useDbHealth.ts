import { useState, useEffect, useCallback, useRef } from "react"
import { getAPIUrl } from "../services/api"
import type { ConnectionState } from "./useApiHealth"
import { useSmartInterval } from "./useSmartInterval"

export function useDbHealth(): ConnectionState {
  const [state, setState] = useState<ConnectionState>("connecting")
  const abortRef = useRef<AbortController | null>(null)

  const check = useCallback(async () => {
    if (abortRef.current) {
      abortRef.current.abort()
    }
    abortRef.current = new AbortController()

    try {
      const resp = await fetch(getAPIUrl("/readiness"), {
        signal: abortRef.current.signal,
      })
      setState(resp.ok ? "connected" : "disconnected")
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") return
      setState("disconnected")
    }
  }, [])

  useSmartInterval({ callback: check, intervalMs: 60_000 })

  useEffect(() => {
    return () => {
      if (abortRef.current) abortRef.current.abort()
    }
  }, [])

  return state
}
