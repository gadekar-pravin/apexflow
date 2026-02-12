import { Plus, Trash2, MessageSquare } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import type { AgentChatSession } from "@/types"

interface ChatSessionListProps {
  sessions: AgentChatSession[]
  currentSessionId: string | null
  onSelect: (id: string) => void
  onCreate: () => void
  onDelete: (id: string) => void
}

export function ChatSessionList({
  sessions,
  currentSessionId,
  onSelect,
  onCreate,
  onDelete,
}: ChatSessionListProps) {
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between px-4 pt-5 pb-4">
        <h2 className="text-sm font-medium text-foreground">Chats</h2>
        <Button variant="ghost" size="icon" onClick={onCreate} className="h-7 w-7">
          <Plus className="h-3.5 w-3.5" />
        </Button>
      </div>
      <div className="mx-4 h-px bg-border/40" />
      <ScrollArea className="flex-1">
        <div className="p-2 space-y-0.5">
          {sessions.length === 0 && (
            <p className="px-3 py-6 text-xs text-muted-foreground text-center">
              No conversations yet
            </p>
          )}
          {sessions.map((session) => (
            <div
              key={session.id}
              className={`group flex items-center gap-2 rounded-lg px-3 py-2.5 text-sm cursor-pointer transition-colors ${
                currentSessionId === session.id
                  ? "bg-foreground/[0.06] text-foreground border border-foreground/10"
                  : "text-muted-foreground hover:bg-muted/60 hover:text-foreground border border-transparent"
              }`}
              onClick={() => onSelect(session.id)}
            >
              <MessageSquare className={`h-3.5 w-3.5 shrink-0 ${currentSessionId === session.id ? "fill-foreground/15" : ""}`} />
              <span className="flex-1 truncate">{session.title}</span>
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  onDelete(session.id)
                }}
                className="hidden group-hover:flex h-5 w-5 items-center justify-center rounded text-muted-foreground hover:text-destructive transition-colors"
              >
                <Trash2 className="h-3 w-3" />
              </button>
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  )
}
