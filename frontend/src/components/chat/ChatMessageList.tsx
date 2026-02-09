import { useEffect, useRef } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { Bot } from "lucide-react"
import type { AgentChatMessage } from "@/types"

interface ChatMessageListProps {
  messages: AgentChatMessage[]
  isRunning: boolean
}

export function ChatMessageList({ messages, isRunning }: ChatMessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, isRunning])

  return (
    <div className="flex-1 overflow-y-auto p-8">
      <div className="max-w-3xl mx-auto space-y-6">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            {msg.role === "assistant" && (
              <div className="mr-3 mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
                <Bot className="h-4 w-4" />
              </div>
            )}
            <div
              className={
                msg.role === "user"
                  ? "max-w-[75%] rounded-2xl rounded-tr-sm bg-primary px-4 py-2.5 text-primary-foreground"
                  : "max-w-[75%] prose prose-sm dark:prose-invert prose-p:my-1 prose-headings:mt-3 prose-headings:mb-1 prose-pre:bg-muted prose-pre:border prose-pre:border-border"
              }
            >
              {msg.role === "user" ? (
                <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
              ) : (
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {msg.content}
                </ReactMarkdown>
              )}
            </div>
          </div>
        ))}

        {isRunning && (
          <div className="flex justify-start">
            <div className="mr-3 mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
              <Bot className="h-4 w-4" />
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
