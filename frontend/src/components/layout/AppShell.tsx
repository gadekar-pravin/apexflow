import { Outlet } from "react-router-dom"
import { Loader2 } from "lucide-react"
import { Sidebar } from "./Sidebar"
import { TooltipProvider } from "@/components/ui/tooltip"
import { StatusBar } from "@/components/StatusBar"
import { AuthProvider, useAuth } from "@/contexts/AuthContext"
import { SSEProvider } from "@/contexts/SSEContext"
import { ExecutionMetricsProvider } from "@/contexts/ExecutionMetricsContext"

function AppContent() {
  const auth = useAuth()

  if (auth.isInitializing) {
    return (
      <div className="flex items-center justify-center h-screen bg-background bg-gradient-radial">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <SSEProvider>
      <ExecutionMetricsProvider>
        <TooltipProvider>
          <div className="flex flex-col h-screen overflow-hidden bg-background bg-gradient-radial">
            <div className="flex flex-1 overflow-hidden">
              <Sidebar />
              <main className="flex-1 overflow-auto">
                <Outlet />
              </main>
            </div>
            <StatusBar />
          </div>
        </TooltipProvider>
      </ExecutionMetricsProvider>
    </SSEProvider>
  )
}

export function AppShell() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  )
}
