import { useQuery } from "@tanstack/react-query"
import {
  FileText,
  Loader2,
} from "lucide-react"
import { cn, formatShortDate } from "@/utils/utils"
import { ScrollArea } from "@/components/ui/scroll-area"
import { ragService } from "@/services"
import { useAppStore } from "@/store"
import type { V2Document } from "@/types"

interface DocumentRowProps {
  doc: V2Document
}

function DocumentRow({ doc }: DocumentRowProps) {
  const { selectedDocumentPath, setSelectedDocumentPath } = useAppStore()
  const isSelected = selectedDocumentPath === doc.id

  return (
    <button
      className={cn(
        "flex items-center gap-2 w-full px-3 py-2 text-sm rounded-md",
        "hover:bg-accent/60 hover:backdrop-blur-xs text-left transition-all duration-150",
        isSelected && "bg-accent/70 backdrop-blur-xs shadow-sm"
      )}
      onClick={() => setSelectedDocumentPath(doc.id, doc.filename)}
    >
      <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
      <span className="truncate flex-1">{doc.filename}</span>
      {doc.chunk_count != null && (
        <span className="text-xs text-muted-foreground">
          {doc.chunk_count} chunks
        </span>
      )}
      <span className="text-xs text-muted-foreground">
        {formatShortDate(doc.created_at)}
      </span>
    </button>
  )
}

export function DocumentTree() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["documents"],
    queryFn: () => ragService.getDocuments(),
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-8">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-4 text-sm text-destructive">
        Failed to load documents: {(error as Error).message}
      </div>
    )
  }

  if (!data?.documents?.length) {
    return (
      <div className="p-4 text-sm text-muted-foreground text-center">
        No documents found. Index documents via the API to get started.
      </div>
    )
  }

  return (
    <ScrollArea className="h-full">
      <div className="p-2 space-y-0.5">
        {data.documents.map((doc) => (
          <DocumentRow key={doc.id} doc={doc} />
        ))}
      </div>
    </ScrollArea>
  )
}
