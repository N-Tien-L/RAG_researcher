"use client"

import { ExternalLink, Globe } from "lucide-react"
import { cn } from "@/lib/utils"
import type { Source } from "@/lib/types"

interface SourceCardProps {
  source: Source
  index: number
  compact?: boolean
}

function getFaviconUrl(url: string) {
  try {
    const { hostname } = new URL(url)
    return `https://www.google.com/s2/favicons?domain=${hostname}&sz=32`
  } catch {
    return null
  }
}

function getDomain(url: string) {
  try {
    return new URL(url).hostname.replace("www.", "")
  } catch {
    return url
  }
}

export function SourceCard({ source, index, compact = false }: SourceCardProps) {
  const sourceLink = source.url || source.source_uri || '#'
  const faviconUrl = getFaviconUrl(sourceLink)
  const domain = getDomain(sourceLink)

  if (compact) {
    return (
      <a
        href={sourceLink}
        target="_blank"
        rel="noopener noreferrer"
        className={cn(
          "inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium",
          "bg-source-bg border border-source-border text-source-text",
          "hover:bg-primary/10 hover:border-primary/30 hover:text-primary",
          "transition-colors cursor-pointer no-underline"
        )}
        title={source.title}
      >
        <span className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-primary/20 text-primary text-[10px] font-bold shrink-0">
          {index + 1}
        </span>
        {faviconUrl ? (
          <img src={faviconUrl} alt="" className="w-3 h-3 rounded-sm shrink-0" aria-hidden="true" />
        ) : (
          <Globe className="w-3 h-3 shrink-0" aria-hidden="true" />
        )}
        <span className="truncate max-w-[100px]">{domain}</span>
      </a>
    )
  }

  return (
    <a
      href={sourceLink}
      target="_blank"
      rel="noopener noreferrer"
      className={cn(
        "group flex flex-col gap-2 p-3 rounded-xl border no-underline",
        "bg-source-bg border-source-border",
        "hover:bg-primary/5 hover:border-primary/25",
        "transition-all duration-150 cursor-pointer"
      )}
    >
      {/* Domain row */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 min-w-0">
          {faviconUrl ? (
            <img
              src={faviconUrl}
              alt=""
              className="w-4 h-4 rounded-sm shrink-0"
              aria-hidden="true"
            />
          ) : (
            <Globe className="w-4 h-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          )}
          <span className="text-[11px] text-muted-foreground truncate font-medium">{domain}</span>
        </div>
        <ExternalLink className="w-3 h-3 shrink-0 text-muted-foreground/50 group-hover:text-primary transition-colors" />
      </div>

      {/* Title */}
      <p className="text-xs font-medium text-foreground leading-relaxed line-clamp-2 group-hover:text-primary transition-colors">
        {source.title}
      </p>

      {/* Snippet */}
      {source.snippet && (
        <p className="text-[11px] text-muted-foreground leading-relaxed line-clamp-2">
          {source.snippet}
        </p>
      )}

      {/* Citation badge */}
      <div className="flex items-center gap-1 mt-auto">
        <span className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-primary/15 text-primary text-[9px] font-bold">
          {index + 1}
        </span>
        <span className="text-[10px] text-muted-foreground/70">Source {index + 1}</span>
      </div>
    </a>
  )
}

export function SourcesGrid({ sources }: { sources: Source[] }) {
  if (!sources || sources.length === 0) return null

  return (
    <div className="mt-4">
      <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-widest mb-3 flex items-center gap-1.5">
        <Globe className="w-3.5 h-3.5" />
        Sources
        <span className="ml-1 inline-flex items-center justify-center w-4 h-4 rounded-full bg-muted text-muted-foreground text-[10px]">
          {sources.length}
        </span>
      </h3>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
        {sources.map((source, i) => (
          <SourceCard key={source.id} source={source} index={i} />
        ))}
      </div>
    </div>
  )
}
