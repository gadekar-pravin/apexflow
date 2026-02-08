import { create } from "zustand"

interface AppState {
  // UI state
  theme: "light" | "dark" | "system"

  // Selected items
  selectedRunId: string | null
  selectedNodeId: string | null
  selectedDocumentPath: string | null

  // Actions
  setTheme: (theme: "light" | "dark" | "system") => void
  setSelectedRunId: (id: string | null) => void
  setSelectedNodeId: (id: string | null) => void
  setSelectedDocumentPath: (path: string | null) => void
}

export const useAppStore = create<AppState>((set) => ({
  // Initial state
  theme: "light",
  selectedRunId: null,
  selectedNodeId: null,
  selectedDocumentPath: null,

  // Actions
  setTheme: (theme) => {
    set({ theme })
    // Apply theme to document
    const root = document.documentElement
    if (theme === "system") {
      const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches
      root.classList.toggle("dark", prefersDark)
    } else {
      root.classList.toggle("dark", theme === "dark")
    }
  },
  setSelectedRunId: (id) => set({ selectedRunId: id, selectedNodeId: null }),
  setSelectedNodeId: (id) => set({ selectedNodeId: id }),
  setSelectedDocumentPath: (path) => set({ selectedDocumentPath: path }),
}))
