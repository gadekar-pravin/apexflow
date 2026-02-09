import { Outlet } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { Loader2, ShieldAlert } from "lucide-react"
import { Sidebar } from "./Sidebar"
import { TooltipProvider } from "@/components/ui/tooltip"
import { Button } from "@/components/ui/button"
import { StatusBar } from "@/components/StatusBar"
import { AuthProvider, useAuth } from "@/contexts/AuthContext"
import { SignInScreen } from "@/components/auth/SignInScreen"
import { SSEProvider } from "@/contexts/SSEContext"
import { ExecutionMetricsProvider } from "@/contexts/ExecutionMetricsContext"
import { fetchAPI, isForbiddenError } from "@/services/api"

function AppContent() {
  const auth = useAuth()

  const authzCheck = useQuery({
    queryKey: ["authz-check"],
    queryFn: () => fetchAPI("/api/runs?limit=1"),
    enabled: auth.isConfigured && auth.isAuthenticated,
    retry: false,
    staleTime: Infinity,
  })

  if (auth.isInitializing) {
    return (
      <div className="flex items-center justify-center h-screen bg-background bg-gradient-radial">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (auth.isConfigured && !auth.isAuthenticated) {
    return <SignInScreen />
  }

  if (auth.isConfigured && auth.isAuthenticated) {
    if (isForbiddenError(authzCheck.error)) {
      return (
        <div className="flex items-center justify-center h-screen bg-background bg-gradient-radial">
          <div className="flex flex-col items-center gap-4 max-w-md text-center">
            <div className="flex items-center justify-center h-16 w-16 rounded-full bg-destructive/10">
              <ShieldAlert className="h-8 w-8 text-destructive" />
            </div>
            <h1 className="text-2xl font-semibold tracking-tight">Access Denied</h1>
            <p className="text-muted-foreground">
              Your account ({auth.user?.email}) is not authorized to use this application.
            </p>
            <p className="text-sm text-muted-foreground">
              Contact the administrator to request access.
            </p>
            <Button variant="outline" onClick={() => auth.signOut()}>
              Sign out
            </Button>
          </div>
        </div>
      )
    }

    if (!authzCheck.isSuccess) {
      return (
        <div className="flex items-center justify-center h-screen bg-background bg-gradient-radial">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      )
    }
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
