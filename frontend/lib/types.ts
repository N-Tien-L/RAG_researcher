export type ChatRole = "user" | "assistant" | "system"

export interface User {
  id: string
  email: string
  username?: string
  created_at: string
}

export interface Source {
  id: string
  type: "pdf" | "youtube" | "text"
  title: string
  status: "processing" | "ready" | "failed"
  user_id: string
  created_at: string
  source_uri?: string
  source_key?: string
  external_id?: string
  content_hash?: string
  last_ingested_at?: string
  updated_at?: string
  url?: string
  snippet?: string
  publishedAt?: string
}

export interface Message {
  id: string
  chat_id: string
  role: ChatRole
  content: string
  sources?: Source[]
  isStreaming?: boolean
  created_at: string
}

export interface ChatMessageRead {
  id: string
  chat_id: string
  role: ChatRole
  content: string
  created_at: string
}

export const mapChatMessageReadToMessage = (
  message: ChatMessageRead,
): Message => ({
  id: message.id,
  chat_id: message.chat_id,
  role: message.role,
  content: message.content,
  created_at: message.created_at,
  sources: (message as any).sources
    ? (message as any).sources.map((source: any, index: number) => {
        const metadata = source?.metadata || {}
        const chunkId = source?.chunk_id || `source-${index + 1}`
        const sourceUri = metadata?.source_uri || ''
        const chunkText = source?.chunk_text || source?.text || metadata?.chunk_text || metadata?.text || metadata?.content || ''
        const type: any = sourceUri?.toLowerCase?.()?.includes('youtube') ? 'youtube' : sourceUri?.toLowerCase?.()?.endsWith('.pdf') ? 'pdf' : 'text'

        return {
          id: chunkId,
          type,
          title: metadata?.source_name || chunkId,
          status: 'ready',
          user_id: '',
          created_at: new Date().toISOString(),
          url: sourceUri,
          source_uri: sourceUri || undefined,
          snippet: chunkText ? String(chunkText).slice(0, 200) : undefined,
        }
      })
    : undefined,
})

export interface ChatSession {
  id: string
  user_id: string
  title?: string
  collections: string[]
  created_at: string
}
