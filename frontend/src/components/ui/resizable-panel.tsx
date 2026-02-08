import * as React from "react"
import { cn } from "@/utils/utils"

interface ResizablePanelProps {
  children: React.ReactNode
  defaultWidth: number
  minWidth: number
  maxWidth: number
  storageKey: string
  side?: "left" | "right"
  className?: string
}

function getStoredWidth(
  storageKey: string,
  defaultWidth: number,
  minWidth: number,
  maxWidth: number
): number {
  if (typeof window === "undefined") {
    return defaultWidth
  }
  try {
    const stored = localStorage.getItem(storageKey)
    if (stored) {
      const parsed = parseInt(stored, 10)
      if (!isNaN(parsed) && parsed >= minWidth && parsed <= maxWidth) {
        return parsed
      }
    }
  } catch {
    // localStorage access blocked or unavailable
  }
  return defaultWidth
}

function saveWidth(storageKey: string, width: number): void {
  try {
    localStorage.setItem(storageKey, width.toString())
  } catch {
    // localStorage access blocked or unavailable
  }
}

export function ResizablePanel({
  children,
  defaultWidth,
  minWidth,
  maxWidth,
  storageKey,
  side = "right",
  className,
}: ResizablePanelProps) {
  const [width, setWidth] = React.useState(() =>
    getStoredWidth(storageKey, defaultWidth, minWidth, maxWidth)
  )

  const [isDragging, setIsDragging] = React.useState(false)

  const dragStateRef = React.useRef<{
    startX: number
    startWidth: number
    handleMouseMove: (e: MouseEvent) => void
    handleMouseUp: () => void
    handleBlur: () => void
    prevCursor: string
    prevUserSelect: string
  } | null>(null)

  const cleanup = React.useCallback(() => {
    const state = dragStateRef.current
    if (!state) return

    document.removeEventListener("mousemove", state.handleMouseMove)
    document.removeEventListener("mouseup", state.handleMouseUp)
    window.removeEventListener("blur", state.handleBlur)
    document.body.style.cursor = state.prevCursor
    document.body.style.userSelect = state.prevUserSelect
    dragStateRef.current = null
    setIsDragging(false)
  }, [])

  React.useEffect(() => {
    return cleanup
  }, [cleanup])

  const handleMouseDown = React.useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault()

      const prevCursor = document.body.style.cursor
      const prevUserSelect = document.body.style.userSelect

      const handleMouseMove = (e: MouseEvent) => {
        const state = dragStateRef.current
        if (!state) return
        const delta = e.clientX - state.startX
        // For left-side handle, dragging left (negative delta) increases width
        const adjustedDelta = side === "left" ? -delta : delta
        const newWidth = Math.min(maxWidth, Math.max(minWidth, state.startWidth + adjustedDelta))
        setWidth(newWidth)
      }

      const handleMouseUp = () => {
        cleanup()
      }

      const handleBlur = () => {
        cleanup()
      }

      dragStateRef.current = {
        startX: e.clientX,
        startWidth: width,
        handleMouseMove,
        handleMouseUp,
        handleBlur,
        prevCursor,
        prevUserSelect,
      }
      setIsDragging(true)

      document.addEventListener("mousemove", handleMouseMove)
      document.addEventListener("mouseup", handleMouseUp)
      window.addEventListener("blur", handleBlur)
      document.body.style.cursor = "col-resize"
      document.body.style.userSelect = "none"
    },
    [width, minWidth, maxWidth, side, cleanup]
  )

  React.useEffect(() => {
    saveWidth(storageKey, width)
  }, [width, storageKey])

  return (
    <div className={cn("relative flex-shrink-0", className)} style={{ width }}>
      {children}
      <div
        onMouseDown={handleMouseDown}
        className={cn(
          "absolute top-0 h-full w-1 cursor-col-resize transition-colors",
          side === "left" ? "left-0" : "right-0",
          "hover:bg-primary/30",
          isDragging && "bg-primary/50"
        )}
      />
    </div>
  )
}
