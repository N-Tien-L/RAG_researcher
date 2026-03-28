"use client"

import { useState } from "react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Skeleton } from "@/components/ui/skeleton"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  MessageSquare,
  Plus,
  Search,
  ChevronLeft,
  ChevronRight,
  Trash2,
  BookOpen,
  Sparkles,
  LogOut,
  UserCircle2,
  MoreHorizontal,
} from "lucide-react"
import type { ChatSession } from "@/lib/types"

interface SidebarProps {
  sessions: ChatSession[]
  isLoading?: boolean
  activeChatId: string | null
  onSelectChat: (id: string) => void
  onNewChat: () => void
  onDeleteChat: (id: string) => void
  onRenameChat: (id: string) => void
  userEmail: string | null
  onSignOut: () => void
  collapsed: boolean
  onToggleCollapse: () => void
}

const groupSessionsByDate = (sessions: ChatSession[]) => {
  const today = new Date()
  today.setHours(0, 0, 0, 0)

  const yesterday = new Date(today)
  yesterday.setDate(yesterday.getDate() - 1)

  const lastWeek = new Date(today)
  lastWeek.setDate(lastWeek.getDate() - 7)

  const groups: Record<string, ChatSession[]> = {
    Today: [],
    Yesterday: [],
    "Last 7 days": [],
    Older: [],
  }

  sessions.forEach((session) => {
    const date = new Date(session.created_at)
    date.setHours(0, 0, 0, 0)
    if (date.getTime() === today.getTime()) {
      groups["Today"].push(session)
    } else if (date.getTime() === yesterday.getTime()) {
      groups["Yesterday"].push(session)
    } else if (date >= lastWeek) {
      groups["Last 7 days"].push(session)
    } else {
      groups["Older"].push(session)
    }
  })

  return groups
}

const truncateChatTitle = (title: string, maxLength: number = 36): string => {
  const normalized = title.replace(/\s+/g, " ").trim()
  if (normalized.length <= maxLength) {
    return normalized
  }

  return `${normalized.slice(0, maxLength - 3).trimEnd()}...`
}

export function Sidebar({
  sessions,
  isLoading = false,
  activeChatId,
  onSelectChat,
  onNewChat,
  onDeleteChat,
  onRenameChat,
  userEmail,
  onSignOut,
  collapsed,
  onToggleCollapse,
}: SidebarProps) {
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState("")

  const filtered = sessions.filter((s) =>
    (s.title ?? "Untitled chat")
      .toLowerCase()
      .includes(searchQuery.toLowerCase())
  )

  const groups = groupSessionsByDate(filtered)

  return (
    <aside
      className={cn(
        "flex flex-col h-full bg-sidebar border-r border-sidebar-border transition-all duration-300 ease-in-out relative",
        collapsed ? "w-14" : "w-76"
      )}
      aria-label="Chat history sidebar"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-4 border-b border-sidebar-border shrink-0">
        {!collapsed && (
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-primary flex items-center justify-center shrink-0">
              <Sparkles className="w-4 h-4 text-primary-foreground" />
            </div>
            <span className="font-semibold text-sm text-sidebar-foreground tracking-tight">
              Nexus
            </span>
          </div>
        )}
        {collapsed && (
          <div className="w-7 h-7 rounded-lg bg-primary flex items-center justify-center mx-auto">
            <Sparkles className="w-4 h-4 text-primary-foreground" />
          </div>
        )}
      </div>

      {/* New Chat Button */}
      <div className={cn("px-2 py-3 shrink-0", collapsed && "px-1.5")}>
        <Button
          type="button"
          onClick={onNewChat}
          className={cn(
            "w-full h-9 text-sm font-medium bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 shadow-none transition-colors",
            collapsed && "px-0 justify-center"
          )}
          variant="ghost"
        >
          <Plus className="w-4 h-4 shrink-0" />
          {!collapsed && <span className="ml-1.5">New chat</span>}
        </Button>
      </div>

      {/* Search */}
      {!collapsed && (
        <div className="px-2 pb-2 shrink-0">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
            <input
              type="text"
              placeholder="Search chats..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full h-8 pl-8 pr-3 text-xs rounded-md bg-background border border-border text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>
        </div>
      )}

      {/* Sessions list */}
      <ScrollArea className="flex-1 min-h-0">
        <div className={cn("px-2 pb-4", collapsed && "px-1.5")}>
          {isLoading && !collapsed && (
            <div className="space-y-2 pt-2">
              <Skeleton className="h-3 w-16 rounded" />
              <Skeleton className="h-8 w-full rounded-md" />
              <Skeleton className="h-8 w-full rounded-md" />
              <Skeleton className="h-8 w-full rounded-md" />
              <Skeleton className="h-3 w-20 rounded mt-3" />
              <Skeleton className="h-8 w-full rounded-md" />
              <Skeleton className="h-8 w-full rounded-md" />
            </div>
          )}

          {isLoading && collapsed && (
            <div className="space-y-2 pt-2">
              {Array.from({ length: 6 }).map((_, index) => (
                <Skeleton key={index} className="h-9 w-full rounded-md" />
              ))}
            </div>
          )}

          {!isLoading && (
            <>
              {Object.entries(groups).map(([group, items]) => {
                if (items.length === 0) return null
                return (
                  <div key={group} className="mb-4">
                    {!collapsed && (
                      <p className="mb-2 px-2 py-1 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/70">
                        {group}
                      </p>
                    )}
                    <ul className="space-y-1">
                      {items.map((session) => {
                        const fullTitle = (session.title || "Untitled chat").trim() || "Untitled chat"
                        const shortTitle = truncateChatTitle(fullTitle)

                        return (
                        <li key={session.id}>
                          <div
                            role="button"
                            tabIndex={0}
                            onClick={() => onSelectChat(session.id)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter" || e.key === " ") {
                                e.preventDefault()
                                onSelectChat(session.id)
                              }
                            }}
                            onMouseEnter={() => setHoveredId(session.id)}
                            onMouseLeave={() => setHoveredId(null)}
                            className={cn(
                              "w-full min-w-0 flex items-center gap-2 rounded-md border transition-all text-left group cursor-pointer",
                              collapsed ? "h-9 justify-center px-0" : "h-9 px-2",
                              activeChatId === session.id
                                ? "bg-sidebar-accent text-sidebar-accent-foreground border-sidebar-border/70 shadow-sm"
                                : "text-sidebar-foreground border-transparent hover:bg-sidebar-accent/50 hover:border-sidebar-border/30"
                            )}
                            title={fullTitle}
                          >
                            <MessageSquare
                              className={cn(
                                "shrink-0 transition-colors",
                                collapsed ? "w-4 h-4" : "w-3.5 h-3.5",
                                activeChatId === session.id
                                  ? "text-primary"
                                  : "text-muted-foreground"
                              )}
                            />
                            {!collapsed && (
                              <>
                                <span className="flex-1 min-w-0 truncate text-xs text-left">
                                  {shortTitle}
                                </span>
                                <div className="shrink-0">
                                  <DropdownMenu>
                                    <DropdownMenuTrigger asChild>
                                      <div
                                        onClick={(e) => e.stopPropagation()}
                                        className="p-1 rounded-md hover:bg-muted-foreground/5 transition-colors cursor-pointer"
                                        aria-label="Chat options"
                                      >
                                        <MoreHorizontal className="w-4 h-4 text-muted-foreground" />
                                      </div>
                                    </DropdownMenuTrigger>
                                    <DropdownMenuContent side="right" align="start">
                                      <DropdownMenuItem onClick={() => onRenameChat(session.id)}>
                                        Rename
                                      </DropdownMenuItem>
                                      <DropdownMenuSeparator />
                                      <DropdownMenuItem
                                        onClick={() => onDeleteChat(session.id)}
                                      >
                                        <Trash2 className="w-3.5 h-3.5 mr-2" />
                                        Delete
                                      </DropdownMenuItem>
                                    </DropdownMenuContent>
                                  </DropdownMenu>
                                </div>
                              </>
                            )}
                          </div>
                        </li>
                        )
                      })}
                    </ul>
                  </div>
                )
              })}

              {filtered.length === 0 && !collapsed && (
                <div className="flex flex-col items-center gap-2 py-8 text-center">
                  <BookOpen className="w-8 h-8 text-muted-foreground/40" />
                  <p className="text-xs text-muted-foreground">
                    {searchQuery ? "No chats found" : "No chats yet"}
                  </p>
                </div>
              )}
            </>
          )}
        </div>
      </ScrollArea>

      <div className={cn("shrink-0 px-2 py-2 border-t border-sidebar-border", collapsed && "px-1.5")}>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              className={cn(
                "w-full h-9 text-sidebar-foreground hover:bg-sidebar-accent/60",
                collapsed ? "justify-center px-0" : "justify-start px-2"
              )}
            >
              <UserCircle2 className="w-4 h-4 shrink-0" />
              {!collapsed && (
                <span className="ml-2 truncate text-xs">
                  {userEmail ?? "Account"}
                </span>
              )}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align={collapsed ? "center" : "start"} side="top" className="w-56">
            <DropdownMenuLabel className="truncate text-xs text-muted-foreground">
              {userEmail ?? "Signed in"}
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={onSignOut}>
              <LogOut className="w-4 h-4" />
              Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {/* Collapse toggle */}
      <div className="shrink-0 px-2 py-3 border-t border-sidebar-border">
        <Button
          variant="ghost"
          size="icon"
          className={cn(
            "h-8 w-8 text-muted-foreground hover:text-foreground hover:bg-sidebar-accent/60",
            collapsed && "mx-auto flex"
          )}
          onClick={onToggleCollapse}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? (
            <ChevronRight className="w-4 h-4" />
          ) : (
            <ChevronLeft className="w-4 h-4" />
          )}
        </Button>
      </div>
    </aside>
  )
}