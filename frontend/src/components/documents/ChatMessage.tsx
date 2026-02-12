import { memo } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { Bot, User } from "lucide-react"
import { cn } from "@/utils/utils"
import type { ChatMessage as ChatMessageType } from "@/types"

interface ChatMessageProps {
  message: ChatMessageType
}

function ChatMessageComponent({ message }: ChatMessageProps) {
  const isUser = message.role === "user"

  return (
    <div
      className={cn(
        "flex gap-3 p-4",
        isUser ? "bg-muted/50" : "bg-background"
      )}
    >
      <div
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
          isUser ? "bg-foreground" : "bg-secondary"
        )}
      >
        {isUser ? (
          <User className="h-4 w-4 text-background" />
        ) : (
          <Bot className="h-4 w-4 text-secondary-foreground" />
        )}
      </div>
      <div className="flex-1 space-y-2 overflow-hidden">
        <p className="text-sm font-medium">
          {isUser ? "You" : "Assistant"}
        </p>
        <div className="prose prose-sm dark:prose-invert max-w-none">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              // Custom rendering for code blocks
              pre: ({ children }) => (
                <pre className="bg-muted rounded-md p-4 overflow-x-auto">
                  {children}
                </pre>
              ),
              code: ({ className, children, ...props }) => {
                const match = /language-(\w+)/.exec(className || "")
                const isInline = !match
                return isInline ? (
                  <code
                    className="bg-muted px-1 py-0.5 rounded text-sm"
                    {...props}
                  >
                    {children}
                  </code>
                ) : (
                  <code className={className} {...props}>
                    {children}
                  </code>
                )
              },
              // Handle images
              img: ({ src, alt }) => (
                <img
                  src={src}
                  alt={alt || ""}
                  className="max-w-full h-auto rounded-md"
                />
              ),
              // Handle links
              a: ({ href, children }) => (
                <a
                  href={href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-foreground underline underline-offset-2 hover:opacity-80"
                >
                  {children}
                </a>
              ),
            }}
          >
            {message.content}
          </ReactMarkdown>
        </div>
        {message.images && message.images.length > 0 && (
          <div className="flex gap-2 flex-wrap mt-2">
            {message.images.map((img, idx) => (
              <img
                key={idx}
                src={img.startsWith("data:") ? img : `data:image/png;base64,${img}`}
                alt={`Attachment ${idx + 1}`}
                className="max-h-48 rounded-md border"
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export const ChatMessage = memo(ChatMessageComponent)
