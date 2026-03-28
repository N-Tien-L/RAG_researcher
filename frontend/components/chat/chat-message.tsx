"use client"

import { useState } from "react"
import { cn } from "@/lib/utils"
import { SourceCard, SourcesGrid } from "./source-card"
import { Button } from "@/components/ui/button"
import {
  Copy,
  Check,
  RefreshCw,
  ThumbsUp,
  ThumbsDown,
  ChevronDown,
  ChevronUp,
  Sparkles,
  User,
} from "lucide-react"
import type { Message } from "@/lib/types"

interface ChatMessageProps {
  message: Message
  onRegenerate?: () => void
}

function CitationInline({ index }: { index: number }) {
  return (
    <span className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-primary/15 text-primary text-[9px] font-bold mx-0.5 align-text-bottom cursor-default select-none">
      {index}
    </span>
  )
}

function parseContentWithCitations(content: string) {
  const parts = content.split(/(\[\d+\])/g)
  return parts.map((part, i) => {
    const match = part.match(/^\[(\d+)\]$/)
    if (match) {
      return <CitationInline key={i} index={parseInt(match[1])} />
    }
    return <span key={i}>{part}</span>
  })
}

function FormattedContent({ content }: { content: string }) {
  const lines = content.split("\n")
  const elements: React.ReactNode[] = []
  let i = 0

  while (i < lines.length) {
    const line = lines[i]

    if (line.startsWith("### ")) {
      elements.push(
        <h3 key={i} className="text-sm font-semibold text-foreground mt-4 mb-1.5 first:mt-0">
          {parseContentWithCitations(line.slice(4))}
        </h3>
      )
    } else if (line.startsWith("## ")) {
      elements.push(
        <h2 key={i} className="text-base font-semibold text-foreground mt-5 mb-2 first:mt-0">
          {parseContentWithCitations(line.slice(3))}
        </h2>
      )
    } else if (line.startsWith("**") && line.endsWith("**") && line.length > 4) {
      elements.push(
        <p key={i} className="text-sm font-semibold text-foreground mt-3 mb-1">
          {parseContentWithCitations(line.slice(2, -2))}
        </p>
      )
    } else if (line.startsWith("- ") || line.startsWith("• ")) {
      elements.push(
        <li key={i} className="text-sm text-foreground leading-relaxed ml-4 list-disc">
          {parseContentWithCitations(line.slice(2))}
        </li>
      )
    } else if (line.match(/^\d+\. /)) {
      const match = line.match(/^(\d+)\. (.*)/)
      if (match) {
        elements.push(
          <li key={i} className="text-sm text-foreground leading-relaxed ml-4 list-decimal">
            {parseContentWithCitations(match[2])}
          </li>
        )
      }
    } else if (line === "") {
      elements.push(<div key={i} className="h-2" />)
    } else {
      elements.push(
        <p key={i} className="text-sm text-foreground leading-relaxed">
          {parseContentWithCitations(line)}
        </p>
      )
    }
    i++
  }

  return <div className="space-y-0.5">{elements}</div>
}

function StreamingIndicator() {
  return (
    <span className="inline-flex gap-0.5 ml-1 align-middle" aria-label="Loading">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="w-1.5 h-1.5 rounded-full bg-primary animate-bounce"
          style={{ animationDelay: `${i * 0.15}s` }}
        />
      ))}
    </span>
  )
}

export function ChatMessage({ message, onRegenerate }: ChatMessageProps) {
  const [copied, setCopied] = useState(false)
  const [showAllSources, setShowAllSources] = useState(false)
  const [feedback, setFeedback] = useState<"up" | "down" | null>(null)

  const isAssistant = message.role === "assistant"
  const hasSources = isAssistant && message.sources && message.sources.length > 0
  const visibleSources = showAllSources
    ? message.sources ?? []
    : (message.sources ?? []).slice(0, 4)

  const handleCopy = async () => {
    await navigator.clipboard.writeText(message.content)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  if (message.role === "user") {
    return (
      <div className="flex items-start gap-3 group py-2">
        <div className="w-7 h-7 rounded-full bg-secondary border border-border flex items-center justify-center shrink-0 mt-0.5">
          <User className="w-3.5 h-3.5 text-muted-foreground" />
        </div>
        <div className="flex-1 min-w-0 pt-0.5">
          <p className="text-sm text-foreground leading-relaxed">{message.content}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex items-start gap-3 group py-2">
      {/* Avatar */}
      <div className="w-7 h-7 rounded-full bg-primary/10 border border-primary/20 flex items-center justify-center shrink-0 mt-0.5">
        <Sparkles className="w-3.5 h-3.5 text-primary" />
      </div>

      <div className="flex-1 min-w-0 space-y-3">
        {/* Compact source citations above answer */}
        {hasSources && !message.isStreaming && (
          <div className="flex flex-wrap gap-1.5 items-center">
            <span className="text-[11px] text-muted-foreground font-medium mr-0.5">Sources:</span>
            {visibleSources.map((source, i) => (
              <SourceCard key={source.id} source={source} index={i} compact />
            ))}
            {(message.sources?.length ?? 0) > 4 && (
              <button
                onClick={() => setShowAllSources(!showAllSources)}
                className="inline-flex items-center gap-0.5 text-[11px] text-muted-foreground hover:text-primary transition-colors"
              >
                {showAllSources ? (
                  <>
                    <ChevronUp className="w-3 h-3" /> Less
                  </>
                ) : (
                  <>
                    <ChevronDown className="w-3 h-3" /> +{(message.sources?.length ?? 0) - 4} more
                  </>
                )}
              </button>
            )}
          </div>
        )}

        {/* Answer content */}
        <div
          className={cn(
            "rounded-2xl px-4 py-3 border",
            "bg-card border-border"
          )}
        >
          <FormattedContent content={message.content} />
          {message.isStreaming && <StreamingIndicator />}
        </div>

        {/* Full source cards grid */}
        {hasSources && !message.isStreaming && (
          <SourcesGrid sources={showAllSources ? (message.sources ?? []) : []} />
        )}

        {/* Action bar */}
        {!message.isStreaming && (
          <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 text-muted-foreground hover:text-foreground"
              onClick={handleCopy}
              aria-label="Copy response"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-primary" /> : <Copy className="w-3.5 h-3.5" />}
            </Button>

            {onRegenerate && (
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 text-muted-foreground hover:text-foreground"
                onClick={onRegenerate}
                aria-label="Regenerate response"
              >
                <RefreshCw className="w-3.5 h-3.5" />
              </Button>
            )}

            <div className="w-px h-4 bg-border mx-0.5" />

            <Button
              variant="ghost"
              size="icon"
              className={cn(
                "h-7 w-7 transition-colors",
                feedback === "up"
                  ? "text-primary"
                  : "text-muted-foreground hover:text-foreground"
              )}
              onClick={() => setFeedback(feedback === "up" ? null : "up")}
              aria-label="Thumbs up"
            >
              <ThumbsUp className="w-3.5 h-3.5" />
            </Button>

            <Button
              variant="ghost"
              size="icon"
              className={cn(
                "h-7 w-7 transition-colors",
                feedback === "down"
                  ? "text-destructive"
                  : "text-muted-foreground hover:text-foreground"
              )}
              onClick={() => setFeedback(feedback === "down" ? null : "down")}
              aria-label="Thumbs down"
            >
              <ThumbsDown className="w-3.5 h-3.5" />
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}
