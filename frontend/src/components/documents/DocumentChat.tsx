import { MessageSquare } from "lucide-react"

interface DocumentChatProps {
  documentPath: string
}

export function DocumentChat({ documentPath }: DocumentChatProps) {
  return (
    <div className="flex h-full flex-col items-center justify-center">
      <div className="text-center max-w-md px-8">
        <div className="flex justify-center mb-6">
          <div className="h-14 w-14 rounded-xl backdrop-blur-glass bg-primary/10 border border-primary/20 flex items-center justify-center">
            <MessageSquare className="h-7 w-7 text-primary/80" strokeWidth={1.5} />
          </div>
        </div>
        <h2 className="text-xl font-semibold tracking-tight mb-2">
          Document Chat
        </h2>
        <p className="text-muted-foreground text-sm leading-relaxed mb-4">
          Document chat is not yet available in v2. The streaming endpoint is being developed.
        </p>
        <p className="text-xs text-muted-foreground">
          Selected: {documentPath}
        </p>
      </div>
    </div>
  )
}
