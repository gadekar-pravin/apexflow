import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Send, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { runsService } from "@/services"
import { useAuth } from "@/contexts/AuthContext"
import { useAppStore } from "@/store"

export function RunCreator() {
  const [query, setQuery] = useState("")
  const queryClient = useQueryClient()
  const setSelectedRunId = useAppStore((s) => s.setSelectedRunId)
  const auth = useAuth()
  const canCreateRun = !auth.isConfigured || auth.isAuthenticated

  const createRun = useMutation({
    mutationFn: (q: string) => runsService.create({ query: q }),
    onSuccess: (data) => {
      setQuery("")
      setSelectedRunId(data.id)
      queryClient.invalidateQueries({ queryKey: ["runs"] })
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (canCreateRun && query.trim()) {
      createRun.mutate(query.trim())
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      handleSubmit(e)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-2.5">
      <Textarea
        placeholder="Describe what you want the agents to do..."
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={handleKeyDown}
        rows={3}
        className="resize-none text-sm bg-background/70 backdrop-blur-xs border-border/50 focus-visible:border-primary/50 focus-visible:ring-primary/15 focus-visible:shadow-[0_0_12px_-3px_hsl(var(--primary)/0.2)]"
      />
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground/70">
          ⌘+Enter to submit
        </span>
        <Button
          type="submit"
          disabled={!canCreateRun || !query.trim() || createRun.isPending}
          size="sm"
        >
          {createRun.isPending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Send className="h-3.5 w-3.5" strokeWidth={1.75} />
          )}
          <span className="ml-1.5">Run</span>
        </Button>
      </div>
    </form>
  )
}
