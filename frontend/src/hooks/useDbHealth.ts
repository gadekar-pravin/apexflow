import { useState, useEffect, useCallback, useRef } from "react"
import { getAPIUrl } from "../services/api"
import type { ConnectionState } from "./useApiHealth"

const DB_HEALTH_INTERVAL = 30000 // 30 seconds

export function useDbHealth(): ConnectionState {
  const [state, setState] = useState<ConnectionState>("connecting")
  const intervalRef = useRef<NodeJS.Timeout | null>(null)
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

  useEffect(() => {
    check()
    intervalRef.current = setInterval(check, DB_HEALTH_INTERVAL)
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
      if (abortRef.current) abortRef.current.abort()
    }
  }, [check])

  return state
}
