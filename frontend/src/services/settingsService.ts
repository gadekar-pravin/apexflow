import { fetchAPI } from "./api"
import type { Settings, CronJob } from "@/types"

export const settingsService = {
  // Get all settings
  async get(): Promise<Settings> {
    const response = await fetchAPI<{ status: string; settings: Settings }>("/api/settings")
    return response.settings
  },

  // Update settings (v2 expects {settings: {...}} wrapper)
  async update(settings: Partial<Settings>): Promise<{ status: string }> {
    return fetchAPI("/api/settings", {
      method: "PUT",
      body: JSON.stringify({ settings }),
    })
  },

  // Reset to defaults
  async reset(): Promise<{ status: string }> {
    return fetchAPI("/api/settings/reset", { method: "POST" })
  },

  // Health check (v2 uses /liveness at root level, no /api prefix)
  async healthCheck(): Promise<{ status: string }> {
    return fetchAPI("/liveness")
  },

  // Skills list (v2 replaced MCP tools with skills — different shape)
  async getMCPTools(): Promise<{ name: string; description: string }[]> {
    try {
      return await fetchAPI<{ name: string; description: string }[]>("/api/skills")
    } catch {
      return []
    }
  },

  // Cron jobs
  async getCronJobs(): Promise<CronJob[]> {
    return fetchAPI<CronJob[]>("/api/cron/jobs")
  },

  async createCronJob(job: Omit<CronJob, "id">): Promise<CronJob> {
    return fetchAPI("/api/cron/jobs", {
      method: "POST",
      body: JSON.stringify(job),
    })
  },

  // Update cron job (not available in v2 — only create/delete)
  async updateCronJob(_id: string, _job: Partial<CronJob>): Promise<never> {
    throw new Error("Not available in v2")
  },

  async deleteCronJob(id: string): Promise<{ status: string }> {
    return fetchAPI(`/api/cron/jobs/${id}`, { method: "DELETE" })
  },

  async runCronJob(id: string): Promise<{ status: string }> {
    return fetchAPI(`/api/cron/jobs/${id}/trigger`, { method: "POST" })
  },
}
