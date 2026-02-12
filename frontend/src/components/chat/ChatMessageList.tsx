import { useCallback, useEffect, useRef, useState } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { Sparkles, Copy, Check } from "lucide-react"
import type { AgentChatMessage } from "@/types"

/** Extract markdown_report from assistant content that may be raw JSON. */
function extractDisplayContent(content: string): string {
  if (!content.trimStart().startsWith("{")) return content
  try {
    const parsed = JSON.parse(content)
    if (parsed && typeof parsed === "object") {
      return parsed.markdown_report || parsed.result || parsed.output || content
    }
  } catch { /* not JSON, render as-is */ }
  return content
}

interface ChatMessageListProps {
  messages: AgentChatMessage[]
  isRunning: boolean
}

export function ChatMessageList({ messages, isRunning }: ChatMessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const [copiedId, setCopiedId] = useState<string | null>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, isRunning])

  const handleCopy = useCallback((text: string, id: string) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopiedId(id)
      setTimeout(() => setCopiedId(null), 2000)
    })
  }, [])

  return (
    <div className="flex-1 overflow-y-auto px-6 py-4">
      <div className="max-w-4xl mx-auto space-y-5">
        {messages.map((msg) => {
          const displayContent = msg.role === "assistant"
            ? extractDisplayContent(msg.content)
            : msg.content

          return (
            <div
              key={msg.id}
              className={`group relative flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              {msg.role === "assistant" && (
                <div className="mr-3 mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-foreground/[0.06] text-foreground">
                  <Sparkles className="h-4 w-4" />
                </div>
              )}
              <div
                className={
                  msg.role === "user"
                    ? "relative max-w-[75%] rounded-2xl rounded-tr-sm bg-foreground px-4 py-2.5 text-background"
                    : "relative max-w-[75%] prose prose-sm dark:prose-invert prose-p:my-1 prose-headings:mt-3 prose-headings:mb-1 prose-pre:bg-muted prose-pre:border prose-pre:border-border"
                }
              >
                <button
                  onClick={() => handleCopy(displayContent, msg.id)}
                  className={`absolute -top-3 ${msg.role === "user" ? "left-0 -translate-x-full -ml-1" : "right-0 translate-x-full ml-1"} p-1 rounded-md border border-border/40 opacity-0 group-hover:opacity-100 transition-opacity ${
                    msg.role === "user"
                      ? "bg-background text-muted-foreground hover:text-foreground"
                      : "bg-background/80 text-muted-foreground hover:text-foreground"
                  }`}
                  aria-label="Copy message"
                >
                  {copiedId === msg.id ? (
                    <Check className="h-3.5 w-3.5 text-success" strokeWidth={2} />
                  ) : (
                    <Copy className="h-3.5 w-3.5" strokeWidth={1.75} />
                  )}
                </button>
                {msg.role === "user" ? (
                  <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                ) : (
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {displayContent}
                  </ReactMarkdown>
                )}
              </div>
            </div>
          )
        })}

        {isRunning && (
          <div className="flex justify-start">
            <div className="mr-3 mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-foreground/[0.06] text-foreground">
              <Sparkles className="h-4 w-4" />
            </div>
            <div className="flex items-center gap-1.5 px-4 py-2.5 text-muted-foreground text-sm">
              <span>Agents working</span>
              <span className="inline-flex gap-0.5">
                <span className="h-1 w-1 rounded-full bg-current animate-bounce [animation-delay:0ms]" />
                <span className="h-1 w-1 rounded-full bg-current animate-bounce [animation-delay:150ms]" />
                <span className="h-1 w-1 rounded-full bg-current animate-bounce [animation-delay:300ms]" />
              </span>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  )
}
