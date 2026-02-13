import { useEffect, useRef, useCallback } from "react"

interface UseSmartIntervalOptions {
  callback: () => void
  intervalMs?: number
  idleTimeoutMs?: number
  fireOnResume?: boolean
  enabled?: boolean
}

const DEFAULT_INTERVAL = 60_000 // 60 seconds
const DEFAULT_IDLE_TIMEOUT = 300_000 // 5 minutes
const ACTIVITY_THROTTLE = 1_000 // 1 second

const ACTIVITY_EVENTS: (keyof DocumentEventMap)[] = [
  "mousemove",
  "mousedown",
  "keydown",
  "touchstart",
  "scroll",
]

export function useSmartInterval({
  callback,
  intervalMs = DEFAULT_INTERVAL,
  idleTimeoutMs = DEFAULT_IDLE_TIMEOUT,
  fireOnResume = true,
  enabled = true,
}: UseSmartIntervalOptions) {
  const callbackRef = useRef(callback)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const idleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastActivityRef = useRef(0)
  const isPausedRef = useRef(false)

  // Keep callback ref fresh
  useEffect(() => {
    callbackRef.current = callback
  }, [callback])

  const clearPolling = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
  }, [])

  const clearIdleTimer = useCallback(() => {
    if (idleTimerRef.current) {
      clearTimeout(idleTimerRef.current)
      idleTimerRef.current = null
    }
  }, [])

  const startPolling = useCallback(() => {
    clearPolling()
    isPausedRef.current = false
    intervalRef.current = setInterval(() => callbackRef.current(), intervalMs)
  }, [intervalMs, clearPolling])

  const startIdleTimer = useCallback(() => {
    clearIdleTimer()
    idleTimerRef.current = setTimeout(() => {
      clearPolling()
      isPausedRef.current = true
    }, idleTimeoutMs)
  }, [idleTimeoutMs, clearIdleTimer, clearPolling])

  const resume = useCallback(() => {
    if (fireOnResume) {
      callbackRef.current()
    }
    startPolling()
    startIdleTimer()
  }, [fireOnResume, startPolling, startIdleTimer])

  useEffect(() => {
    if (!enabled) return

    // Fire immediately on mount, start interval + idle timer
    callbackRef.current()
    startPolling()
    startIdleTimer()

    const handleVisibilityChange = () => {
      if (document.hidden) {
        clearPolling()
        clearIdleTimer()
        isPausedRef.current = true
      } else {
        resume()
      }
    }

    const handleActivity = () => {
      const now = Date.now()
      if (now - lastActivityRef.current < ACTIVITY_THROTTLE) return
      lastActivityRef.current = now

      if (isPausedRef.current) {
        resume()
      } else {
        // Reset idle timer on activity
        startIdleTimer()
      }
    }

    document.addEventListener("visibilitychange", handleVisibilityChange)
    for (const event of ACTIVITY_EVENTS) {
      document.addEventListener(event, handleActivity, { passive: true })
    }

    return () => {
      clearPolling()
      clearIdleTimer()
      document.removeEventListener("visibilitychange", handleVisibilityChange)
      for (const event of ACTIVITY_EVENTS) {
        document.removeEventListener(event, handleActivity)
      }
    }
  }, [enabled, startPolling, startIdleTimer, clearPolling, clearIdleTimer, resume])
}
