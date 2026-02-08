import { fetchAPI } from "./api"
import type {
  RunRequest,
  RunResponse,
  RunSummary,
  RunDetail,
  UserInputRequest,
} from "@/types"

export const runsService = {
  // Create a new run
  async create(request: RunRequest): Promise<RunResponse> {
    return fetchAPI<RunResponse>("/api/runs/execute", {
      method: "POST",
      body: JSON.stringify(request),
    })
  },

  // List all runs
  async list(): Promise<RunSummary[]> {
    return fetchAPI<RunSummary[]>("/api/runs")
  },

  // Get a specific run with graph
  async get(runId: string): Promise<RunDetail> {
    return fetchAPI<RunDetail>(`/api/runs/${runId}`)
  },

  // Stop a running execution
  async stop(runId: string): Promise<{ id: string; status: string }> {
    return fetchAPI<{ id: string; status: string }>(`/api/runs/${runId}/stop`, {
      method: "POST",
    })
  },

  // Delete a run
  async delete(runId: string): Promise<{ id: string; status: string }> {
    return fetchAPI<{ id: string; status: string }>(`/api/runs/${runId}`, {
      method: "DELETE",
    })
  },

  // Provide user input to a running agent
  async provideInput(
    runId: string,
    input: UserInputRequest
  ): Promise<{ id: string; status: string; stored_as: string }> {
    return fetchAPI<{ id: string; status: string; stored_as: string }>(
      `/api/runs/${runId}/input`,
      {
        method: "POST",
        body: JSON.stringify(input),
      }
    )
  },

  // Test a specific agent node (not available in v2)
  async testAgent(
    _runId: string,
    _nodeId: string,
    _input?: string
  ): Promise<never> {
    throw new Error("Not available in v2")
  },

  // Save agent test results (not available in v2)
  async saveAgentTest(
    _runId: string,
    _nodeId: string,
    _output: Record<string, unknown>,
    _executionResult?: Record<string, unknown>
  ): Promise<never> {
    throw new Error("Not available in v2")
  },
}
