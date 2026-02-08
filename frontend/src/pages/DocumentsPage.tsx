import { useMutation, useQueryClient } from "@tanstack/react-query"
import { RefreshCw, Loader2, FileText } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ResizablePanel } from "@/components/ui/resizable-panel"
import { DocumentTree, DocumentChat } from "@/components/documents"
import { ragService } from "@/services"
import { useAppStore } from "@/store"

export function DocumentsPage() {
  const { selectedDocumentPath } = useAppStore()
  const queryClient = useQueryClient()

  const reindex = useMutation({
    mutationFn: () => ragService.reindex(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents"] })
    },
  })

  return (
    <div className="flex h-full">
      {/* Left sidebar - Document tree */}
      <ResizablePanel
        defaultWidth={288}
        minWidth={200}
        maxWidth={600}
        storageKey="apexflow.documents.sidebarWidth"
        className="border-r border-border/40 flex flex-col backdrop-blur-glass bg-sidebar/40"
      >
        <div className="flex items-center justify-between px-4 pt-5 pb-4">
          <h2 className="text-sm font-medium">Documents</h2>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 text-muted-foreground hover:text-foreground"
            onClick={() => reindex.mutate()}
            disabled={reindex.isPending}
          >
            {reindex.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <RefreshCw className="h-3.5 w-3.5" strokeWidth={1.75} />
            )}
          </Button>
        </div>
        <div className="mx-4 divider-fade" />
        <div className="flex-1 overflow-hidden">
          <DocumentTree />
        </div>
      </ResizablePanel>

      {/* Main content - Chat */}
      <div className="flex-1 flex flex-col bg-background">
        {selectedDocumentPath ? (
          <>
            <div className="border-b border-border/40 px-6 py-4 backdrop-blur-xs bg-card/30">
              <h2 className="text-sm font-medium truncate">{selectedDocumentPath}</h2>
            </div>
            <div className="flex-1 overflow-hidden">
              <DocumentChat documentPath={selectedDocumentPath} />
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center max-w-md px-8">
              <div className="flex justify-center mb-6">
                <div className="h-14 w-14 rounded-xl backdrop-blur-glass bg-muted/40 border border-white/10 flex items-center justify-center glow-on-hover transition-all duration-300">
                  <FileText className="h-7 w-7 text-muted-foreground" strokeWidth={1.5} />
                </div>
              </div>
              <h2 className="text-xl font-semibold tracking-tight mb-2">
                Document Chat
              </h2>
              <p className="text-muted-foreground text-sm leading-relaxed">
                Select a document from the sidebar to start chatting about its contents.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
