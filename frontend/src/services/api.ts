// Base API configuration

const API_URL = import.meta.env.VITE_API_URL || ""

export async function fetchAPI<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_URL}${endpoint}`

  const response = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(error.detail || `API Error: ${response.status}`)
  }

  return response.json()
}

export function getAPIUrl(endpoint: string): string {
  return `${API_URL}${endpoint}`
}

export { API_URL }
