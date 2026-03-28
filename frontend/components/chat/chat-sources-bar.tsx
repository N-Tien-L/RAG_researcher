"use client"

import { useRef, useState } from "react"
import { cn } from "@/lib/utils"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Spinner } from "@/components/ui/spinner"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import type { Source } from "@/lib/types"
import { ApiError } from "@/lib/api/client"
import { toast } from "sonner"
import { Plus, Youtube, Paperclip } from "lucide-react"

interface ChatSourcesBarProps {
  activeChatId: string | null
  linkedSources: Source[]
  pendingSources: Source[]
  onAddPdf: (file: File) => Promise<void>
  onAddYoutube: (url: string) => Promise<void>
  isLoadingSources: boolean
}

const statusDot = (status: Source["status"]) => {
  if (status === "ready") return "bg-emerald-500"
  if (status === "failed") return "bg-rose-500"
  return "bg-amber-500"
}

export function ChatSourcesBar({
  activeChatId,
  linkedSources,
  pendingSources,
  onAddPdf,
  onAddYoutube,
  isLoadingSources,
}: ChatSourcesBarProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const [isDialogOpen, setIsDialogOpen] = useState(false)
  const [youtubeUrl, setYoutubeUrl] = useState("")
  const [isUploadingPdf, setIsUploadingPdf] = useState(false)
  const [isAddingYoutube, setIsAddingYoutube] = useState(false)
  const [isDragging, setIsDragging] = useState(false)

  const displaySources = activeChatId ? linkedSources : pendingSources

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setIsUploadingPdf(true)
    try {
      await onAddPdf(file)
      setIsDialogOpen(false)
      toast.success("File uploaded and processing started.")
    } catch (error) {
      if (!(error instanceof ApiError && error.notified)) {
        toast.error("Unable to upload file right now.")
      }
    } finally {
      setIsUploadingPdf(false)
      if (fileInputRef.current) fileInputRef.current.value = ""
    }
  }

  const handleDrop = async (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragging(false)
    const file = e.dataTransfer.files?.[0]
    if (!file || file.type !== "application/pdf") {
      toast.error("Only PDF files are supported.")
      return
    }
    setIsUploadingPdf(true)
    try {
      await onAddPdf(file)
      setIsDialogOpen(false)
      toast.success("File uploaded and processing started.")
    } catch (error) {
      if (!(error instanceof ApiError && error.notified)) {
        toast.error("Unable to upload file right now.")
      }
    } finally {
      setIsUploadingPdf(false)
    }
  }

  const handleAddYoutube = async () => {
    if (!youtubeUrl.trim()) {
      toast.error("Please paste a YouTube URL.")
      return
    }
    setIsAddingYoutube(true)
    try {
      await onAddYoutube(youtubeUrl.trim())
      setYoutubeUrl("")
      setIsDialogOpen(false)
      toast.success("YouTube source added and processing started.")
    } catch (error) {
      if (!(error instanceof ApiError && error.notified)) {
        toast.error("Unable to add YouTube source right now.")
      }
    } finally {
      setIsAddingYoutube(false)
    }
  }

  return (
    <div className="border-t border-border px-4 py-2 flex items-center gap-2 flex-wrap min-h-[40px]">
      <span className="text-xs font-medium text-muted-foreground shrink-0">Sources:</span>

      {isLoadingSources ? (
        <Spinner className="w-3.5 h-3.5 text-muted-foreground" />
      ) : displaySources.length === 0 ? (
        <span className="text-xs text-muted-foreground/60 italic">
          No sources — add one to enable RAG
        </span>
      ) : (
        <div className="flex items-center gap-1.5 flex-wrap">
          {displaySources.map((source) => (
            <Badge
              key={source.id}
              variant="outline"
              className="gap-1.5 text-xs py-0.5 px-2 max-w-[180px]"
            >
              <span
                className={cn("h-1.5 w-1.5 rounded-full shrink-0", statusDot(source.status))}
                aria-hidden
              />
              <span className="truncate">{source.title}</span>
            </Badge>
          ))}
          {!activeChatId && pendingSources.length > 0 && (
            <span className="text-xs text-amber-600 ml-1">
              Will be linked when chat starts
            </span>
          )}
        </div>
      )}

      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="h-6 gap-1 px-2 text-xs text-muted-foreground hover:text-foreground ml-auto shrink-0"
        onClick={() => setIsDialogOpen(true)}
      >
        <Plus className="w-3 h-3" />
        Add source
      </Button>

      <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Add source</DialogTitle>
            <DialogDescription>
              Upload a PDF or add a YouTube video as a RAG source.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            {/* PDF upload */}
            <div className="space-y-2">
              <p className="text-sm font-medium">PDF file</p>
              <div
                className={cn(
                  "flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-6 cursor-pointer transition-colors",
                  isDragging
                    ? "border-primary bg-primary/5"
                    : "border-border hover:border-primary/50 hover:bg-muted/40"
                )}
                onClick={() => fileInputRef.current?.click()}
                onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
                onDragLeave={() => setIsDragging(false)}
                onDrop={(e) => void handleDrop(e)}
              >
                {isUploadingPdf ? (
                  <Spinner className="w-5 h-5 text-muted-foreground" />
                ) : (
                  <>
                    <Paperclip className="w-5 h-5 text-muted-foreground mb-1" />
                    <p className="text-xs text-muted-foreground text-center">
                      Click or drag a PDF here to upload
                    </p>
                  </>
                )}
              </div>
              <input
                ref={fileInputRef}
                type="file"
                accept="application/pdf"
                className="hidden"
                onChange={(e) => void handleFileChange(e)}
              />
            </div>

            <div className="relative flex items-center gap-2">
              <div className="flex-1 h-px bg-border" />
              <span className="text-xs text-muted-foreground">or</span>
              <div className="flex-1 h-px bg-border" />
            </div>

            {/* YouTube URL */}
            <div className="space-y-2">
              <p className="text-sm font-medium flex items-center gap-1.5">
                <Youtube className="w-3.5 h-3.5" />
                YouTube URL
              </p>
              <div className="flex gap-2">
                <Input
                  value={youtubeUrl}
                  onChange={(e) => setYoutubeUrl(e.target.value)}
                  placeholder="https://www.youtube.com/watch?v=..."
                  disabled={isAddingYoutube}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") void handleAddYoutube()
                  }}
                />
                <Button
                  type="button"
                  size="sm"
                  onClick={() => void handleAddYoutube()}
                  disabled={isAddingYoutube || !youtubeUrl.trim()}
                >
                  {isAddingYoutube ? (
                    <Spinner className="w-3.5 h-3.5" />
                  ) : (
                    "Add"
                  )}
                </Button>
              </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
