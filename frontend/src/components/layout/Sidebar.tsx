import { NavLink } from "react-router-dom"
import {
  Play,
  FileText,
  Settings,
  Hexagon,
} from "lucide-react"
import { cn } from "@/utils/utils"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"

const navItems = [
  {
    title: "Dashboard",
    href: "/",
    icon: Play,
    description: "Agent execution & graph view",
    end: true,
  },
  {
    title: "Documents",
    href: "/documents",
    icon: FileText,
    description: "RAG document management",
  },
  {
    title: "Settings",
    href: "/settings",
    icon: Settings,
    description: "System configuration",
  },
]

export function Sidebar() {
  return (
    <aside className="flex h-full w-14 flex-col border-r border-border/40 backdrop-blur-glass bg-sidebar/60">
      {/* Logo */}
      <div className="flex h-14 items-center justify-center">
        <div className="group flex h-8 w-8 items-center justify-center rounded-md bg-primary shadow-sm transition-all duration-200 hover:shadow-glow-sm hover:scale-105">
          <Hexagon className="h-4 w-4 text-primary-foreground transition-transform duration-200 group-hover:scale-110" strokeWidth={2.5} />
        </div>
      </div>

      {/* Divider */}
      <div className="mx-3 h-px bg-border/40" />

      {/* Navigation */}
      <nav className="flex-1 space-y-0.5 p-2 pt-3">
        {navItems.map((item) => (
          <Tooltip key={item.href} delayDuration={200}>
            <TooltipTrigger asChild>
              <NavLink
                to={item.href}
                end={"end" in item && !!item.end}
                className={({ isActive }) =>
                  cn(
                    "group flex items-center justify-center rounded-md p-2.5 transition-all duration-150",
                    isActive
                      ? "bg-primary/10 text-primary shadow-sm [&_svg]:text-primary"
                      : "text-muted-foreground hover:bg-muted/60 hover:text-foreground [&_svg]:text-muted-foreground [&_svg]:group-hover:text-foreground"
                  )
                }
              >
                <item.icon className="h-4 w-4 shrink-0 transition-colors" strokeWidth={1.75} />
                <span className="sr-only">{item.title}</span>
              </NavLink>
            </TooltipTrigger>
            <TooltipContent side="right" className="flex flex-col gap-0.5">
              <span className="font-medium">{item.title}</span>
              <span className="text-xs text-muted-foreground">
                {item.description}
              </span>
            </TooltipContent>
          </Tooltip>
        ))}
      </nav>
    </aside>
  )
}
