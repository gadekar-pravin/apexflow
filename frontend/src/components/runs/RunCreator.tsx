import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Play, Loader2 } from "lucide-react"
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
    <form onSubmit={handleSubmit}>
      <div className="rounded-2xl bg-card shadow-lg shadow-foreground/[0.04] border border-border/60 p-4 transition-shadow focus-within:shadow-xl focus-within:shadow-foreground/[0.06]">
        <textarea
          placeholder="Describe what you want the agents to do..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={3}
          disabled={!canCreateRun || createRun.isPending}
          className="w-full resize-none bg-transparent border-none ring-0 focus:ring-0 focus:outline-none text-sm text-foreground placeholder:text-muted-foreground/40 disabled:cursor-not-allowed disabled:opacity-50"
        />
        <div className="flex items-center justify-between mt-2">
          <span className="text-xs text-muted-foreground/50">
            {navigator.platform?.startsWith("Mac") ? "⌘" : "Ctrl"}+Enter
          </span>
          <Button
            type="submit"
            disabled={!canCreateRun || !query.trim() || createRun.isPending}
            size="sm"
            className="rounded-xl bg-primary text-primary-foreground hover:bg-primary/90"
          >
            {createRun.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Play className="h-3.5 w-3.5 fill-current" strokeWidth={1.75} />
            )}
            <span className="ml-1.5">Run</span>
          </Button>
        </div>
      </div>
    </form>
  )
}
