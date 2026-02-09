import * as React from "react"
import { cn } from "@/utils/utils"

const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.ComponentProps<"textarea">
>(({ className, ...props }, ref) => {
  return (
    <textarea
      className={cn(
        "flex min-h-[60px] w-full rounded-md border border-input bg-background/80 backdrop-blur-xs px-3 py-2 text-sm transition-all duration-150",
        "placeholder:text-muted-foreground/60",
        "focus-visible:outline-none focus-visible:border-primary/50 focus-visible:ring-2 focus-visible:ring-primary/15 focus-visible:shadow-[0_0_12px_-3px_hsl(var(--primary)/0.2)]",
        "disabled:cursor-not-allowed disabled:opacity-50 disabled:bg-muted",
        className
      )}
      ref={ref}
      {...props}
    />
  )
})
Textarea.displayName = "Textarea"

export { Textarea }
