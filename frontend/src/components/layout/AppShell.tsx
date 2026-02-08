import { Outlet } from "react-router-dom"
import { Sidebar } from "./Sidebar"
import { TooltipProvider } from "@/components/ui/tooltip"
import { StatusBar } from "@/components/StatusBar"
import { SSEProvider } from "@/contexts/SSEContext"
import { ExecutionMetricsProvider } from "@/contexts/ExecutionMetricsContext"

export function AppShell() {
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
