import { useRef, useCallback, type KeyboardEvent, type ChangeEvent } from "react"
import { Send } from "lucide-react"
import { Button } from "@/components/ui/button"

interface ChatInputProps {
  value: string
  onChange: (value: string) => void
  onSend: () => void
  disabled?: boolean
  placeholder?: string
}

export function ChatInput({
  value,
  onChange,
  onSend,
  disabled = false,
  placeholder = "Ask anything...",
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

  return (
    <div className="border-t border-border bg-background px-8 py-4">
      <div className="max-w-3xl mx-auto">
        <div className="relative">
          {/* Subtle gradient glow */}
          <div className="absolute -inset-1 rounded-xl bg-gradient-to-r from-primary/10 via-primary/5 to-primary/10 blur-sm opacity-40" />

          <div className="relative flex items-end gap-2 rounded-xl border border-border bg-card p-2 shadow-sm">
            <textarea
              ref={textareaRef}
              value={value}
              onChange={handleChange}
              onKeyDown={handleKeyDown}
              disabled={disabled}
              placeholder={placeholder}
              rows={1}
              className="flex-1 resize-none bg-transparent px-2 py-1.5 text-sm text-foreground placeholder:text-muted-foreground/60 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
              style={{ maxHeight: 160 }}
            />
            <Button
              size="icon"
              onClick={onSend}
              disabled={disabled || !value.trim()}
              className="h-8 w-8 shrink-0 rounded-lg transition-transform hover:scale-105"
            >
              <Send className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
