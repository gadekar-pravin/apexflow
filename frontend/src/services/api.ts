// Base API configuration

const API_URL = import.meta.env.VITE_API_URL || ""

// SSE connects directly to Cloud Run (Firebase Hosting rewrites don't support streaming).
// Falls back to API_URL for local dev where Vite proxy handles it.
const SSE_URL = import.meta.env.VITE_SSE_URL || API_URL

// Auth token provider — set via setAuthTokenProvider() when Firebase is initialized
let authTokenProvider: (() => Promise<string | null>) | null = null

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = "ApiError"
    this.status = status
  }
}

export function setAuthTokenProvider(provider: () => Promise<string | null>) {
  authTokenProvider = provider
}

export function getAuthToken(): Promise<string | null> {
  return authTokenProvider ? authTokenProvider() : Promise.resolve(null)
}

export async function fetchAPI<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_URL}${endpoint}`

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  }

  const token = await getAuthToken()
  if (token) {
    headers["Authorization"] = `Bearer ${token}`
  }

  const response = await fetch(url, {
    ...options,
    headers: {
      ...headers,
      ...options.headers,
    },
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }))
    throw new ApiError(error.detail || `API Error: ${response.status}`, response.status)
  }

  const text = await response.text()
  return text ? JSON.parse(text) as T : undefined as unknown as T
}

export function isUnauthorizedError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401
}

export function isForbiddenError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 403
}

export function getAPIUrl(endpoint: string): string {
  return `${API_URL}${endpoint}`
}

export function getSSEUrl(endpoint: string): string {
  return `${SSE_URL}${endpoint}`
}

export { API_URL }
