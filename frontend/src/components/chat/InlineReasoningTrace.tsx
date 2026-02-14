import { useRef, useEffect } from "react"
import { ChevronDown, ChevronUp } from "lucide-react"
import { StepTimelineItem, type ConsolidatedStep } from "./reasoning-shared"

interface InlineReasoningTraceProps {
  steps: ConsolidatedStep[]
  isLive: boolean
  isExpanded: boolean
  onToggle: () => void
}

function getSummaryText(steps: ConsolidatedStep[], isLive: boolean): string {
  if (isLive) {
    return `Thinking... (${steps.length} step${steps.length !== 1 ? "s" : ""})`
  }

  const failed = steps.find((s) => s.status === "failed")
  if (failed) {
    const idx = steps.indexOf(failed) + 1
    return `Failed at step ${idx}`
  }

  const totalTime = steps.reduce((sum, s) => sum + (s.execution_time ?? 0), 0)
  const timeStr = totalTime > 0 ? ` in ${totalTime.toFixed(1)}s` : ""
  return `${steps.length} step${steps.length !== 1 ? "s" : ""} completed${timeStr}`
}

export function InlineReasoningTrace({ steps, isLive, isExpanded, onToggle }: InlineReasoningTraceProps) {
  const contentRef = useRef<HTMLDivElement>(null)

  // Sync max-height with actual scroll height for smooth CSS transition
  useEffect(() => {
    const el = contentRef.current
    if (!el) return
    if (isExpanded) {
      el.style.maxHeight = `${el.scrollHeight}px`
    } else {
      el.style.maxHeight = "0px"
    }
  }, [isExpanded, steps])

  if (steps.length === 0) return null

  const summary = getSummaryText(steps, isLive)

  return (
    <div className="mb-2">
      <button
        type="button"
        onClick={onToggle}
        className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors bg-transparent border-none p-0 cursor-pointer"
      >
        {isExpanded ? (
          <ChevronUp className="h-3.5 w-3.5" />
        ) : (
          <ChevronDown className="h-3.5 w-3.5" />
        )}
        <span>{summary}</span>
        {isLive && (
          <span className="inline-flex gap-0.5 ml-1">
            <span className="h-1 w-1 rounded-full bg-current animate-bounce [animation-delay:0ms]" />
            <span className="h-1 w-1 rounded-full bg-current animate-bounce [animation-delay:150ms]" />
            <span className="h-1 w-1 rounded-full bg-current animate-bounce [animation-delay:300ms]" />
          </span>
        )}
      </button>

      <div
        ref={contentRef}
        className="overflow-hidden transition-[max-height] duration-200 ease-in-out"
        style={{ maxHeight: isExpanded ? undefined : 0 }}
      >
        <div className="relative pt-2 pl-1">
          {steps.length > 0 && (
            <div className="absolute left-[13px] top-5 bottom-3 w-px bg-border" />
          )}
          <div className="space-y-3">
            {steps.map((step) => (
              <StepTimelineItem key={step.step_id} step={step} />
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
