import { useRef, useCallback, type KeyboardEvent, type ChangeEvent } from "react"
import { Send } from "lucide-react"
import { Button } from "@/components/ui/button"

interface ChatInputProps {
  value: string
  onChange: (value: string) => void
  onSend: () => void
  disabled?: boolean
  placeholder?: string
  /** When true, renders without the fixed-footer wrapper (border-t, bg, padding) */
  inline?: boolean
}

export function ChatInput({
  value,
  onChange,
  onSend,
  disabled = false,
  placeholder = "Ask anything...",
  inline = false,
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault()
        if (value.trim() && !disabled) {
          onSend()
        }
      }
    },
    [value, disabled, onSend]
  )

  const handleChange = useCallback(
    (e: ChangeEvent<HTMLTextAreaElement>) => {
      onChange(e.target.value)
      // Auto-resize
      const el = e.target
      el.style.height = "auto"
      el.style.height = Math.min(el.scrollHeight, 160) + "px"
    },
    [onChange]
  )

  const inputWidget = (
    <div className="relative">
      <div className="relative flex items-center gap-3 bg-card rounded-xl border border-border p-3 shadow-sm transition-colors focus-within:border-foreground/30">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          placeholder={placeholder}
          rows={3}
          className="flex-1 resize-none bg-transparent border-none ring-0 focus:ring-0 focus:outline-none px-2 py-1.5 text-base text-foreground placeholder:text-muted-foreground/50 disabled:cursor-not-allowed disabled:opacity-50 min-h-[5rem]"
          style={{ maxHeight: 200 }}
        />
        <Button
          size="icon"
          onClick={onSend}
          disabled={disabled || !value.trim()}
          className="h-10 w-10 shrink-0 rounded-lg transition-all hover:scale-105 bg-foreground text-background hover:bg-foreground/90"
        >
          <Send className="h-4 w-4" />
        </Button>
      </div>
    </div>
  )

  if (inline) {
    return <div className="max-w-4xl w-full mx-auto">{inputWidget}</div>
  }

  return (
    <div className="border-t border-border bg-background px-6 py-4 shrink-0">
      <div className="max-w-4xl mx-auto">{inputWidget}</div>
    </div>
  )
}
