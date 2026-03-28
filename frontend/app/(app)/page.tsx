"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"

import { ChatInput } from "@/components/chat/chat-input"
import { ChatMessage } from "@/components/chat/chat-message"
import { ChatSourcesBar } from "@/components/chat/chat-sources-bar"
import { Sidebar } from "@/components/chat/sidebar"
import { WelcomeScreen } from "@/components/chat/welcome-screen"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Skeleton } from "@/components/ui/skeleton"

import { useAuth } from "@/hooks/use-auth"
import { useChats } from "@/hooks/use-chats"
import { useMessages } from "@/hooks/use-messages"
import { useSources } from "@/hooks/use-sources"

import { ApiError } from "@/lib/api/client"
import { getChatSources, linkSourceToChat } from "@/lib/api/chats"
import type { Source } from "@/lib/types"
import { toast } from "sonner"

export default function AppHomePage() {
  const { user, logout } = useAuth()

  const { chats, isLoading: isChatsLoading, createChat, deleteChat, updateChatTitle } = useChats()

  const {
    messages,
    isLoadingHistory,
    isSending,
    isStreaming,
    loadHistory,
    sendMessage,
    stopStreaming,
    clearMessages,
  } = useMessages()

  const [activeChatId, setActiveChatId] = useState<string | null>(null)
  const [inputValue, setInputValue] = useState<string>("")
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState<boolean>(false)
  const [isCreatingFreshChat, setIsCreatingFreshChat] = useState<boolean>(false)
  const [pendingSourceIds, setPendingSourceIds] = useState<string[]>([])
  const [pendingSources, setPendingSources] = useState<Source[]>([])
  const [linkedSources, setLinkedSources] = useState<Source[]>([])

  const skipNextHistoryLoad = useRef(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const { uploadPdf, addYoutube, isLoading: isSourcesLoading } = useSources(activeChatId)

  useEffect(() => {
    if (isChatsLoading) return

    if (activeChatId) {
      const exists = chats.some((chat) => chat.id === activeChatId)

      if (!exists) {
        setActiveChatId(null)
        clearMessages()
      }

      return
    }

    if (chats.length > 0 && !isCreatingFreshChat) {
      setActiveChatId(chats[0].id)
    }
  }, [activeChatId, chats, clearMessages, isChatsLoading, isCreatingFreshChat])

  useEffect(() => {
    if (!activeChatId) {
      clearMessages()
      setLinkedSources([])
      return
    }

    if (skipNextHistoryLoad.current) {
      skipNextHistoryLoad.current = false
      return
    }

    void loadHistory(activeChatId).catch((error: unknown) => {
      if (error instanceof ApiError && error.notified) return
      toast.error("Failed to load conversation history.")
    })
  }, [activeChatId, clearMessages, loadHistory])

  useEffect(() => {
    if (!activeChatId) {
      setLinkedSources([])
      return
    }
    void getChatSources(activeChatId).then(setLinkedSources).catch(() => {
      // Non-critical; silently ignore
    })
  }, [activeChatId])

  const handleSourceIngested = useCallback((source: Source) => {
    if (!activeChatId) {
      setPendingSourceIds((prev) => [...prev, source.id])
      setPendingSources((prev) => [...prev, source])
    } else {
      void getChatSources(activeChatId).then(setLinkedSources).catch(() => {})
    }
  }, [activeChatId])

  const handleSelectChat = (chatId: string) => {
    setIsCreatingFreshChat(false)
    setActiveChatId(chatId)
  }

  const handleNewChat = () => {
    setIsCreatingFreshChat(true)
    setActiveChatId(null)
    setInputValue("")
    clearMessages()
  }

  const handleDeleteChat = (chatId: string) => {
    deleteChat(chatId)

    if (activeChatId === chatId) {
      setActiveChatId(null)
      clearMessages()
    }
  }

  const handleRenameSession = async (chatId: string) => {
    const current = chats.find((c) => c.id === chatId)
    const currentTitle = current?.title ?? ""
    const newTitle = window.prompt("Rename chat", currentTitle)
    if (newTitle === null) return // cancelled
    const trimmed = newTitle.trim()
    if (trimmed.length === 0) {
      toast.error("Title cannot be empty")
      return
    }
    try {
      updateChatTitle(chatId, trimmed)
    } catch (error) {
      toast.error("Failed to rename chat")
    }
  }

  const handleRegenerate = async () => {
    if (!activeChatId || isSending) return

    const lastUserMessage = [...messages]
      .reverse()
      .find((message) => message.role === "user")

    if (!lastUserMessage?.content) {
      toast.error("No previous user message found to regenerate from.")
      return
    }

    try {
      await sendMessage(activeChatId, lastUserMessage.content)
    } catch (error) {
      if (error instanceof ApiError && error.notified) return
      toast.error("Failed to regenerate response.")
    }
  }

  const handleSubmit = async (content: string) => {
    if (!content.trim()) return

    try {
      let chatId = activeChatId

      if (!chatId) {
        const created = await createChat(undefined, content)
        chatId = created.id
        setIsCreatingFreshChat(false)
        skipNextHistoryLoad.current = true
        setActiveChatId(chatId)

      }

      // Link any staged pending sources — deduplicate and tolerate per-item
      // conflicts (e.g. duplicate source IDs or already-linked sources).
      if (pendingSourceIds.length > 0) {
        const uniqueIds = [...new Set(pendingSourceIds)]
        const linkedIds: string[] = []
        await Promise.allSettled(
          uniqueIds.map((sourceId) =>
            linkSourceToChat(chatId!, sourceId)
              .then(() => { linkedIds.push(sourceId) })
              .catch(() => { /* silently skip conflicts */ })
          )
        )
        if (linkedIds.length > 0) {
          setPendingSourceIds((prev) => prev.filter((id) => !linkedIds.includes(id)))
          setPendingSources((prev) => prev.filter((s) => !linkedIds.includes(s.id)))
          void getChatSources(chatId!).then(setLinkedSources).catch(() => {})
        }
      }

      setInputValue("")
      const result = await sendMessage(chatId, content)

      if (result.chat_title) {
        updateChatTitle(chatId, result.chat_title)
      }

      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
    } catch (error) {
      if (error instanceof ApiError && error.notified) return
      toast.error("Unable to send message right now.")
    }
  }

  const subtitle = useMemo(() => {
    return user?.email ? `Signed in as ${user.email}` : "Authenticated"
  }, [user?.email])

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <Sidebar
        sessions={chats}
        isLoading={isChatsLoading}
        activeChatId={activeChatId}
        onSelectChat={handleSelectChat}
        onNewChat={handleNewChat}
          onDeleteChat={handleDeleteChat}
          onRenameChat={handleRenameSession}
        userEmail={user?.email ?? null}
        onSignOut={logout}
        collapsed={isSidebarCollapsed}
        onToggleCollapse={() =>
          setIsSidebarCollapsed((prev) => !prev)
        }
      />

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-border px-4 py-3">
          <div>
            <h1 className="text-sm font-semibold text-foreground">
              RAG Researcher
            </h1>
            <p className="text-xs text-muted-foreground">
              {subtitle}
            </p>
          </div>
        </header>

        {messages.length === 0 && !activeChatId && !isLoadingHistory ? (
          <WelcomeScreen
            onSuggestionClick={(prompt) => setInputValue(prompt)}
          />
        ) : (
          <ScrollArea className="min-h-0 flex-1">
            <div className="mx-auto flex w-full max-w-3xl flex-col gap-2 px-4 py-6">
              {isLoadingHistory ? (
                <div className="space-y-4">
                  <div className="flex items-start gap-3">
                    <Skeleton className="mt-1 h-7 w-7 rounded-full" />
                    <div className="flex-1 space-y-2">
                      <Skeleton className="h-4 w-1/2" />
                      <Skeleton className="h-4 w-5/6" />
                    </div>
                  </div>

                  <div className="flex items-start gap-3">
                    <Skeleton className="mt-1 h-7 w-7 rounded-full" />
                    <div className="flex-1 space-y-2">
                      <Skeleton className="h-4 w-2/3" />
                      <Skeleton className="h-4 w-4/5" />
                      <Skeleton className="h-4 w-1/3" />
                    </div>
                  </div>
                </div>
              ) : (
                messages.map((message) => (
                  <ChatMessage
                    key={message.id}
                    message={message}
                    onRegenerate={
                      message.role === "assistant"
                        ? handleRegenerate
                        : undefined
                    }
                  />
                ))
              )}
              <div ref={messagesEndRef} />
            </div>
          </ScrollArea>
        )}

        <ChatSourcesBar
          activeChatId={activeChatId}
          linkedSources={linkedSources}
          pendingSources={pendingSources}
          onAddPdf={async (file) => {
            const source = await uploadPdf(file)
            handleSourceIngested(source)
          }}
          onAddYoutube={async (url) => {
            const source = await addYoutube(url)
            handleSourceIngested(source)
          }}
          isLoadingSources={isSourcesLoading}
        />

        <div className="border-t border-border px-2 py-3 sm:px-4">
          <ChatInput
            activeChatId={activeChatId}
            value={inputValue}
            onChange={setInputValue}
            onSubmit={handleSubmit}
            onStop={stopStreaming}
            isStreaming={isStreaming}
            isSending={isSending}
            disabled={isLoadingHistory || isSending}
            placeholder="Ask a question about your sources..."
          onSourceIngested={handleSourceIngested}
          />
        </div>
      </main>
    </div>
  )
}