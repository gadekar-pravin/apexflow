import { Search, FileText, BarChart3, Lightbulb } from "lucide-react"
import { ChatInput } from "./ChatInput"

const suggestions = [
  {
    icon: Search,
    title: "Search my documents",
    description: "Find insights across your indexed files",
    query: "Search my documents for key findings",
  },
  {
    icon: BarChart3,
    title: "Analyze data",
    description: "Run analysis on uploaded datasets",
    query: "Analyze the data and summarize trends",
  },
  {
    icon: FileText,
    title: "Summarize a document",
    description: "Get a concise summary of any file",
    query: "Summarize my most recent document",
  },
  {
    icon: Lightbulb,
    title: "Brainstorm ideas",
    description: "Generate ideas for a project or topic",
    query: "Help me brainstorm ideas for my project",
  },
]

interface WelcomeScreenProps {
  onSend: (query: string) => void
  inputValue: string
  onInputChange: (value: string) => void
  onInputSend: () => void
  disabled?: boolean
}

export function WelcomeScreen({ onSend, inputValue, onInputChange, onInputSend, disabled }: WelcomeScreenProps) {
  return (
    <div className="flex-1 flex flex-col overflow-y-auto px-4 pt-8 pb-6">
      {/* Centered content block */}
      <div className="flex-1 flex items-center justify-center">
        <div className="max-w-[700px] w-full mx-auto space-y-8 px-6">
          <div className="text-center space-y-2">
            <h1 className="text-2xl font-semibold text-foreground">
              What can I help you with?
            </h1>
            <p className="text-sm text-muted-foreground">
              Ask a question or pick a suggestion below to get started.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3">
            {suggestions.map((item) => (
              <button
                key={item.title}
                onClick={() => onSend(item.query)}
                className="group flex items-start gap-3 rounded-xl border border-border bg-card p-4 text-left transition-colors hover:border-primary/30 hover:bg-muted/50"
              >
                <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary transition-colors group-hover:bg-primary/15">
                  <item.icon className="h-4 w-4" />
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-medium text-foreground">{item.title}</p>
                  <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
                    {item.description}
                  </p>
                </div>
              </button>
            ))}
          </div>

          {/* Inline input below suggestions */}
          <div className="space-y-3">
            <p className="text-center text-sm text-muted-foreground">
              Or type your own question
            </p>
            <ChatInput
              value={inputValue}
              onChange={onInputChange}
              onSend={onInputSend}
              disabled={disabled}
              placeholder="Ask anything about your data..."
              inline
            />
          </div>
        </div>
      </div>
    </div>
  )
}
