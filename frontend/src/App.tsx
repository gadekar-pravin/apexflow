import { useEffect } from "react"
import { BrowserRouter, Routes, Route } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { AppShell } from "@/components/layout"
import { DashboardPage, DocumentsPage, SettingsPage, ChatPage } from "@/pages"
import { useAppStore } from "@/store"
import { isUnauthorizedError, isForbiddenError } from "@/services/api"

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5000,
      refetchOnWindowFocus: false,
      // Avoid retry storms for auth errors (401 unauthenticated, 403 unauthorized).
      retry: (failureCount, error) =>
        !isUnauthorizedError(error) && !isForbiddenError(error) && failureCount < 3,
    },
  },
})

function App() {
  const theme = useAppStore((s) => s.theme)

  // Apply theme class on initial render and when theme changes
  useEffect(() => {
    const root = document.documentElement
    if (theme === "system") {
      const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches
      root.classList.toggle("dark", prefersDark)
    } else {
      root.classList.toggle("dark", theme === "dark")
    }
  }, [theme])

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/" element={<ChatPage />} />
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/documents" element={<DocumentsPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

export default App
