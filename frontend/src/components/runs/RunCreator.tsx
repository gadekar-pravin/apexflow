import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Send, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
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
    <form onSubmit={handleSubmit} className="relative">
      {/* Animated gradient glow behind input */}
      <div className="absolute -inset-1 bg-gradient-to-r from-primary/20 via-blue-500/20 to-primary/20 rounded-2xl blur-sm opacity-60 animate-pulse" />

      <div className="relative rounded-xl border-2 border-primary/30 bg-card p-3 shadow-lg shadow-primary/10 space-y-2.5">
        <textarea
          placeholder="Describe what you want the agents to do..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={3}
          className="w-full resize-none bg-transparent border-none ring-0 focus:ring-0 focus:outline-none text-sm text-foreground placeholder:text-muted-foreground/50 disabled:cursor-not-allowed disabled:opacity-50"
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
      </div>
    </form>
  )
}
