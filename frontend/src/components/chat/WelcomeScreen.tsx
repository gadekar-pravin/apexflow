import { Search, FileText, BarChart3, Lightbulb } from "lucide-react"
import { ChatInput } from "./ChatInput"

const suggestions = [
  {
    icon: Search,
    title: "Search my documents",
    description: "Find insights across your indexed files and databases.",
    query: "Search my documents for key findings",
  },
  {
    icon: BarChart3,
    title: "Analyze data",
    description: "Run analysis on uploaded datasets and spot trends.",
    query: "Analyze the data and summarize trends",
  },
  {
    icon: FileText,
    title: "Summarize a document",
    description: "Get a concise summary of any file in seconds.",
    query: "Summarize my most recent document",
  },
  {
    icon: Lightbulb,
    title: "Brainstorm ideas",
    description: "Generate creative ideas for a project or topic.",
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
    <div className="flex-1 flex flex-col overflow-y-auto px-4 pt-4 pb-4">
      {/* Centered content block */}
      <div className="flex-1 flex items-center justify-center">
        <div className="max-w-4xl w-full mx-auto space-y-8 px-4">
          <div className="text-center space-y-3">
            <h1 className="text-4xl font-bold tracking-tight text-foreground dark:bg-clip-text dark:text-transparent dark:bg-gradient-to-r dark:from-foreground dark:via-foreground/80 dark:to-muted-foreground">
              What can I help you with?
            </h1>
            <p className="text-lg text-muted-foreground font-light">
              Ask a question or pick a suggestion below to get started.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-4">
            {suggestions.map((item) => (
              <button
                key={item.title}
                onClick={() => onSend(item.query)}
                disabled={disabled}
                className="group flex items-start gap-3 rounded-2xl border border-border bg-card p-5 text-left transition-all hover:border-foreground/20 hover:bg-muted/50 disabled:opacity-50 disabled:pointer-events-none"
              >
                <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-foreground/[0.06] text-muted-foreground transition-all group-hover:bg-foreground/10 group-hover:text-foreground group-hover:scale-110">
                  <item.icon className="h-[18px] w-[18px]" />
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-medium text-foreground">{item.title}</p>
                  <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
                    {item.description}
                  </p>
                </div>
              </button>
            ))}
          </div>

          {/* Inline input below suggestions */}
          <div className="space-y-3 mb-10">
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
