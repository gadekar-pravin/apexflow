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
    <div className="relative rounded-2xl bg-card shadow-lg shadow-foreground/[0.04] border border-border/60 p-4 transition-shadow focus-within:shadow-xl focus-within:shadow-foreground/[0.06]">
      <textarea
        ref={textareaRef}
        value={value}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        placeholder={placeholder}
        rows={3}
        className="w-full resize-none bg-transparent border-none ring-0 focus:ring-0 focus:outline-none px-1 py-1 text-base text-foreground placeholder:text-muted-foreground/40 disabled:cursor-not-allowed disabled:opacity-50 min-h-[5rem]"
        style={{ maxHeight: 200 }}
      />
      <div className="flex justify-end mt-2">
        <Button
          size="icon"
          onClick={onSend}
          disabled={disabled || !value.trim()}
          className="h-11 w-11 shrink-0 rounded-xl transition-all hover:scale-105 bg-foreground text-background hover:bg-foreground/90"
        >
          <Send className="h-[18px] w-[18px]" />
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
