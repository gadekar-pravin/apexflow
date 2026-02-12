import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Save, RotateCcw, Loader2, Sun, Moon, Monitor } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { ScrollArea } from "@/components/ui/scroll-area"
import { settingsService } from "@/services"
import { useAuth } from "@/contexts/AuthContext"
import { useAppStore } from "@/store"
import type { Settings } from "@/types"
import { useState, useEffect } from "react"
import { cn } from "@/utils/utils"

function safeInt(val: string, fallback: number): number {
  const n = parseInt(val, 10)
  return Number.isNaN(n) ? fallback : n
}

function safeFloat(val: string, fallback: number): number {
  const n = parseFloat(val)
  return Number.isNaN(n) ? fallback : n
}

const themeOptions = [
  { value: "system" as const, label: "System", icon: Monitor },
  { value: "light" as const, label: "Light", icon: Sun },
  { value: "dark" as const, label: "Dark", icon: Moon },
]

export function SettingsPage() {
  const queryClient = useQueryClient()
  const [localSettings, setLocalSettings] = useState<Settings | null>(null)
  const { theme, setTheme } = useAppStore()
  const auth = useAuth()
  const canQuerySettings = !auth.isConfigured || auth.isAuthenticated

  const { data: settings, isLoading, isError, error } = useQuery({
    queryKey: ["settings"],
    queryFn: () => settingsService.get(),
    enabled: canQuerySettings,
  })

  useEffect(() => {
    if (settings) {
      setLocalSettings(settings)
    }
  }, [settings])

  const updateSettings = useMutation({
    mutationFn: (newSettings: Partial<Settings>) =>
      settingsService.update(newSettings),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["settings"] })
    },
  })

  const resetSettings = useMutation({
    mutationFn: () => settingsService.reset(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["settings"] })
    },
  })

  const handleSave = () => {
    if (localSettings) {
      updateSettings.mutate(localSettings)
    }
  }

  const updateLocalSetting = <K extends keyof Settings>(
    section: K,
    key: keyof Settings[K],
    value: unknown
  ) => {
    if (!localSettings) return
    setLocalSettings({
      ...localSettings,
      [section]: {
        ...localSettings[section],
        [key]: value,
      },
    })
  }

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (isError || !localSettings) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3">
        <p className="text-sm text-destructive">
          {error instanceof Error ? error.message : "Failed to load settings"}
        </p>
        <Button
          variant="outline"
          size="sm"
          onClick={() => queryClient.invalidateQueries({ queryKey: ["settings"] })}
        >
          <RotateCcw className="h-3.5 w-3.5 mr-1.5" strokeWidth={1.75} />
          Retry
        </Button>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-8 py-6 border-b border-border/40 backdrop-blur-xs bg-card/30">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Configure Cortex system settings
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => resetSettings.mutate()}
            disabled={resetSettings.isPending}
            className="text-muted-foreground"
          >
            {resetSettings.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <RotateCcw className="h-3.5 w-3.5" strokeWidth={1.75} />
            )}
            <span className="ml-1.5">Reset</span>
          </Button>
          <Button
            size="sm"
            onClick={handleSave}
            disabled={updateSettings.isPending}
          >
            {updateSettings.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Save className="h-3.5 w-3.5" strokeWidth={1.75} />
            )}
            <span className="ml-1.5">Save Changes</span>
          </Button>
        </div>
      </div>

      {/* Content */}
      <ScrollArea className="flex-1">
        <div className="px-8 py-6 space-y-6 max-w-3xl">
          {/* Appearance Settings */}
          <Card variant="glass" className="glow-on-hover">
            <CardHeader className="pb-4">
              <CardTitle className="text-base font-medium">Appearance</CardTitle>
              <CardDescription className="text-sm">
                Customize the look and feel of the interface
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                <label className="text-sm text-muted-foreground">Theme</label>
                <div className="flex gap-2">
                  {themeOptions.map((option) => (
                    <button
                      key={option.value}
                      onClick={() => setTheme(option.value)}
                      className={cn(
                        "flex items-center gap-2 px-3 py-2 rounded-md text-sm transition-all duration-150",
                        "border backdrop-blur-xs",
                        theme === option.value
                          ? "border-foreground/20 bg-foreground/[0.06] text-foreground font-medium shadow-sm"
                          : "border-border/50 bg-background/50 text-muted-foreground hover:bg-muted/50 hover:text-foreground"
                      )}
                    >
                      <option.icon className="h-4 w-4" strokeWidth={1.75} />
                      {option.label}
                    </button>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Agent Settings */}
          <Card variant="glass" className="glow-on-hover">
            <CardHeader className="pb-4">
              <CardTitle className="text-base font-medium">Agent Configuration</CardTitle>
              <CardDescription className="text-sm">
                Settings for the agent execution engine
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-x-6 gap-y-4">
                <div className="space-y-1.5">
                  <label className="text-sm text-muted-foreground">Default Model</label>
                  <Input
                    value={localSettings.agent.default_model}
                    onChange={(e) =>
                      updateLocalSetting("agent", "default_model", e.target.value)
                    }
                    className="h-9"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-sm text-muted-foreground">Model Provider</label>
                  <Input
                    value={localSettings.agent.model_provider}
                    onChange={(e) =>
                      updateLocalSetting("agent", "model_provider", e.target.value)
                    }
                    className="h-9"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-sm text-muted-foreground">Max Steps</label>
                  <Input
                    type="number"
                    value={localSettings.agent.max_steps}
                    onChange={(e) =>
                      updateLocalSetting("agent", "max_steps", safeInt(e.target.value, localSettings.agent.max_steps))
                    }
                    className="h-9"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-sm text-muted-foreground">Max Lifelines per Step</label>
                  <Input
                    type="number"
                    value={localSettings.agent.max_lifelines_per_step}
                    onChange={(e) =>
                      updateLocalSetting(
                        "agent",
                        "max_lifelines_per_step",
                        safeInt(e.target.value, localSettings.agent.max_lifelines_per_step)
                      )
                    }
                    className="h-9"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-sm text-muted-foreground">Rate Limit Interval (s)</label>
                  <Input
                    type="number"
                    step="0.1"
                    value={localSettings.agent.rate_limit_interval}
                    onChange={(e) =>
                      updateLocalSetting(
                        "agent",
                        "rate_limit_interval",
                        safeFloat(e.target.value, localSettings.agent.rate_limit_interval)
                      )
                    }
                    className="h-9"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-sm text-muted-foreground">Max Cost per Run ($)</label>
                  <Input
                    type="number"
                    step="0.01"
                    value={localSettings.agent.max_cost_per_run}
                    onChange={(e) =>
                      updateLocalSetting(
                        "agent",
                        "max_cost_per_run",
                        safeFloat(e.target.value, localSettings.agent.max_cost_per_run)
                      )
                    }
                    className="h-9"
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* RAG Settings */}
          <Card variant="glass" className="glow-on-hover">
            <CardHeader className="pb-4">
              <CardTitle className="text-base font-medium">RAG Configuration</CardTitle>
              <CardDescription className="text-sm">
                Settings for document indexing and retrieval
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-x-6 gap-y-4">
                <div className="space-y-1.5">
                  <label className="text-sm text-muted-foreground">Chunk Size</label>
                  <Input
                    type="number"
                    value={localSettings.rag.chunk_size}
                    onChange={(e) =>
                      updateLocalSetting("rag", "chunk_size", safeInt(e.target.value, localSettings.rag.chunk_size))
                    }
                    className="h-9"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-sm text-muted-foreground">Chunk Overlap</label>
                  <Input
                    type="number"
                    value={localSettings.rag.chunk_overlap}
                    onChange={(e) =>
                      updateLocalSetting("rag", "chunk_overlap", safeInt(e.target.value, localSettings.rag.chunk_overlap))
                    }
                    className="h-9"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-sm text-muted-foreground">Max Chunk Length</label>
                  <Input
                    type="number"
                    value={localSettings.rag.max_chunk_length}
                    onChange={(e) =>
                      updateLocalSetting(
                        "rag",
                        "max_chunk_length",
                        safeInt(e.target.value, localSettings.rag.max_chunk_length)
                      )
                    }
                    className="h-9"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-sm text-muted-foreground">Top K Results</label>
                  <Input
                    type="number"
                    value={localSettings.rag.top_k}
                    onChange={(e) =>
                      updateLocalSetting("rag", "top_k", safeInt(e.target.value, localSettings.rag.top_k))
                    }
                    className="h-9"
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Models */}
          <Card variant="glass" className="glow-on-hover">
            <CardHeader className="pb-4">
              <CardTitle className="text-base font-medium">Model Configuration</CardTitle>
              <CardDescription className="text-sm">
                Models used for different system components
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-x-6 gap-y-4">
                <div className="space-y-1.5">
                  <label className="text-sm text-muted-foreground">Embedding Model</label>
                  <Input
                    value={localSettings.models.embedding}
                    onChange={(e) =>
                      updateLocalSetting("models", "embedding", e.target.value)
                    }
                    className="h-9"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-sm text-muted-foreground">Semantic Chunking Model</label>
                  <Input
                    value={localSettings.models.semantic_chunking}
                    onChange={(e) =>
                      updateLocalSetting(
                        "models",
                        "semantic_chunking",
                        e.target.value
                      )
                    }
                    className="h-9"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-sm text-muted-foreground">Image Captioning Model</label>
                  <Input
                    value={localSettings.models.image_captioning}
                    onChange={(e) =>
                      updateLocalSetting(
                        "models",
                        "image_captioning",
                        e.target.value
                      )
                    }
                    className="h-9"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-sm text-muted-foreground">Memory Extraction Model</label>
                  <Input
                    value={localSettings.models.memory_extraction}
                    onChange={(e) =>
                      updateLocalSetting(
                        "models",
                        "memory_extraction",
                        e.target.value
                      )
                    }
                    className="h-9"
                  />
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </ScrollArea>
    </div>
  )
}
