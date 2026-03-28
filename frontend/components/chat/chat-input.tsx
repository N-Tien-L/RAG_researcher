"use client"

import { useRef, useEffect, KeyboardEvent, useState } from "react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"
import { Input } from "@/components/ui/input"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { useSources } from "@/hooks/use-sources"
import { ApiError } from "@/lib/api/client"
import type { Source } from "@/lib/types"
import { toast } from "sonner"
import { ArrowUp, Square, Paperclip, Youtube } from "lucide-react"

interface ChatInputProps {
  activeChatId?: string | null
  onSourceIngested?: (source: Source) => void
  value: string
  onChange: (value: string) => void
  onSubmit: (value: string) => void
  onStop?: () => void
  isStreaming?: boolean
  isSending?: boolean
  placeholder?: string
  disabled?: boolean
}

export function ChatInput({
  activeChatId = null,
  onSourceIngested,
  value,
  onChange,
  onSubmit,
  onStop,
  isStreaming = false,
  isSending = false,
  placeholder = "Ask anything...",
  disabled = false,
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const { addYoutube, uploadPdf } = useSources(activeChatId)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const [isUploading, setIsUploading] = useState(false)
  const [isYoutubeDialogOpen, setIsYoutubeDialogOpen] = useState(false)
  const [youtubeUrl, setYoutubeUrl] = useState("")
  const [isAddingYoutube, setIsAddingYoutube] = useState(false)

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = "auto"
    el.style.height = Math.min(el.scrollHeight, 200) + "px"
  }, [value])

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      if (value.trim() && !isStreaming && !disabled) {
        onSubmit(value.trim())
      }
    }
  }

  const handleSubmit = () => {
    if (isStreaming) {
      onStop?.()
      return
    }
    if (value.trim() && !disabled) {
      onSubmit(value.trim())
    }
  }

  const canSubmit = (value.trim().length > 0 || isStreaming) && !disabled && !isSending

  const handleAddYoutube = async () => {
    if (!youtubeUrl.trim()) {
      toast.error("Please paste a YouTube URL.")
      return
    }

    setIsAddingYoutube(true)
    try {
      const result = await addYoutube(youtubeUrl.trim())
      onSourceIngested?.(result)
      setYoutubeUrl("")
      setIsYoutubeDialogOpen(false)
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
    <div className="w-full max-w-3xl mx-auto px-4">
      <div
        className={cn(
          "relative flex flex-col rounded-2xl border transition-all duration-150",
          "bg-card border-border",
          "focus-within:border-primary/50 focus-within:ring-2 focus-within:ring-primary/10",
          "shadow-sm"
        )}
      >
        {/* Textarea */}
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          rows={1}
          className={cn(
            "w-full resize-none bg-transparent px-4 pt-3.5 pb-2",
            "text-sm text-foreground placeholder:text-muted-foreground",
            "focus:outline-none",
            "min-h-[52px] max-h-[200px]",
            "leading-relaxed"
          )}
          aria-label="Chat message input"
        />

        {/* Bottom bar */}
        <div className="flex items-center justify-between px-3 pb-2.5 pt-0.5 gap-2">
          {/* Left tools */}
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 text-muted-foreground hover:text-foreground rounded-lg"
              aria-label="Attach file"
              type="button"
              onClick={() => fileInputRef.current?.click()}
            >
              {isUploading ? (
                <Spinner className="w-3.5 h-3.5" />
              ) : (
                <Paperclip className="w-3.5 h-3.5" />
              )}
            </Button>
            <input
              ref={fileInputRef}
              type="file"
              accept="application/pdf"
              className="hidden"
              onChange={async (e) => {
                const file = e.target.files?.[0]
                if (!file) return

                setIsUploading(true)
                try {
                  const result = await uploadPdf(file)
                  onSourceIngested?.(result)
                  toast.success('File uploaded and processing started.')
                } catch (error) {
                  if (!(error instanceof ApiError && error.notified)) {
                    toast.error('Unable to upload file right now.')
                  }
                } finally {
                  setIsUploading(false)
                  // reset the input so same file can be selected again
                  if (fileInputRef.current) fileInputRef.current.value = ''
                }
              }}
            />
            <Button
              variant="ghost"
              size="sm"
              className="h-7 gap-1.5 px-2 text-xs text-muted-foreground hover:text-foreground rounded-lg"
              aria-label="Add YouTube source"
              type="button"
              onClick={() => setIsYoutubeDialogOpen(true)}
            >
              <Youtube className="w-3.5 h-3.5" />
              <span>YouTube</span>
            </Button>
          </div>

          {/* Right: send/stop */}
          <div className="flex items-center gap-2">
            {value.trim().length > 0 && !isStreaming && (
              <span className="text-[10px] text-muted-foreground/60 hidden sm:block">
                Shift+Enter for newline
              </span>
            )}
            <Button
              onClick={handleSubmit}
              disabled={!canSubmit}
              size="icon"
              className={cn(
                "h-8 w-8 rounded-xl transition-all shrink-0",
                isStreaming
                  ? "bg-foreground text-background hover:bg-foreground/80"
                  : canSubmit
                  ? "bg-primary text-primary-foreground hover:bg-primary/90"
                  : "bg-muted text-muted-foreground cursor-not-allowed"
              )}
              aria-label={isStreaming ? "Stop generating" : "Send message"}
            >
              {isStreaming ? (
                <Square className="w-3.5 h-3.5 fill-current" />
              ) : isSending ? (
                <Spinner className="w-4 h-4" />
              ) : (
                <ArrowUp className="w-4 h-4" strokeWidth={2.5} />
              )}
            </Button>
          </div>
        </div>
      </div>

      <p className="text-center text-[11px] text-muted-foreground/60 mt-2">
        Nexus can make mistakes. Verify important information from sources.
      </p>

      <Dialog open={isYoutubeDialogOpen} onOpenChange={setIsYoutubeDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Add YouTube source</DialogTitle>
            <DialogDescription>
              Paste a YouTube URL to ingest it into your RAG sources.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <Input
              value={youtubeUrl}
              onChange={(e) => setYoutubeUrl(e.target.value)}
              placeholder="https://www.youtube.com/watch?v=..."
              disabled={isAddingYoutube}
            />
            <div className="flex justify-end">
              <Button
                type="button"
                size="sm"
                onClick={() => void handleAddYoutube()}
                disabled={isAddingYoutube}
              >
                {isAddingYoutube ? (
                  <>
                    <Spinner className="mr-2 h-3.5 w-3.5" />
                    Adding...
                  </>
                ) : (
                  "Add source"
                )}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
