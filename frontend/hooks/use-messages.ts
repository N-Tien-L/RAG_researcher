'use client'

import { useCallback, useRef, useState } from 'react'

import {
	getChatHistory,
	sendMessage as sendMessageApi,
	type SendMessageResponse,
} from '@/lib/api/messages'
import {
	mapChatMessageReadToMessage,
	type Message,
	type Source,
} from '@/lib/types'

type UseMessagesResult = {
	messages: Message[]
	isLoadingHistory: boolean
	isSending: boolean
	isStreaming: boolean
	loadHistory: (chatId: string) => Promise<void>
	sendMessage: (chatId: string, content: string) => Promise<{ chat_title?: string | null }>
	stopStreaming: () => void
	clearMessages: () => void
}

const STREAM_MS_PER_WORD = 35

const asRecord = (value: unknown): Record<string, unknown> =>
	typeof value === 'object' && value !== null
		? (value as Record<string, unknown>)
		: {}

const asString = (value: unknown): string | undefined =>
	typeof value === 'string' && value.length > 0 ? value : undefined

const inferSourceType = (uri?: string): Source['type'] => {
	if (!uri) {
		return 'text'
	}

	const normalized = uri.toLowerCase()
	if (normalized.includes('youtube.com') || normalized.includes('youtu.be')) {
		return 'youtube'
	}

	if (normalized.endsWith('.pdf')) {
		return 'pdf'
	}

	return 'text'
}

const mapResponseSources = (sources: SendMessageResponse['sources']): Source[] => {
	return sources.map((source, index) => {
		const payload = asRecord(source)
		const metadata = asRecord(payload.metadata)

		const chunkId = asString(payload.chunk_id) ?? `source-${index + 1}`
		const title = asString(metadata.source_name) ?? chunkId
		const sourceUri = asString(metadata.source_uri) ?? ''
		const chunkText =
			asString(payload.chunk_text) ??
			asString(payload.text) ??
			asString(metadata.chunk_text) ??
			asString(metadata.text) ??
			asString(metadata.content) ??
			''

		return {
			id: chunkId,
			type: inferSourceType(sourceUri),
			title,
			status: 'ready',
			user_id: '',
			created_at: new Date().toISOString(),
			url: sourceUri,
			source_uri: sourceUri || undefined,
			snippet: chunkText ? chunkText.slice(0, 200) : undefined,
		}
	})
}

export const useMessages = (): UseMessagesResult => {
	const [messages, setMessages] = useState<Message[]>([])
	const [isLoadingHistory, setIsLoadingHistory] = useState(false)
	const [isSending, setIsSending] = useState(false)
	const [isStreaming, setIsStreaming] = useState(false)

	const streamTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
	const streamingMessageIdRef = useRef<string | null>(null)
	const streamingFinalContentRef = useRef<string>('')

	const stopStreaming = useCallback(() => {
		if (streamTimerRef.current) {
			clearInterval(streamTimerRef.current)
			streamTimerRef.current = null
		}

		const streamingMessageId = streamingMessageIdRef.current
		if (streamingMessageId) {
			setMessages((prev) =>
				prev.map((message) =>
					message.id === streamingMessageId
						? {
								...message,
								content: streamingFinalContentRef.current,
								isStreaming: false,
							}
						: message,
				),
			)
		}

		streamingMessageIdRef.current = null
		streamingFinalContentRef.current = ''
		setIsStreaming(false)
	}, [])

	const loadHistory = useCallback(
		async (chatId: string) => {
			setIsLoadingHistory(true)
			try {
				const history = await getChatHistory(chatId)
				setMessages(history.map(mapChatMessageReadToMessage))
			} finally {
				setIsLoadingHistory(false)
			}
		},
		[],
	)

	const sendMessage = useCallback(
		async (chatId: string, content: string): Promise<{ chat_title?: string | null }> => {
			if (!content.trim()) {
				return {}
			}

			stopStreaming()
			setIsSending(true)

			try {
				const response = await sendMessageApi(chatId, content)
				const userMessage = mapChatMessageReadToMessage(response.user_message)
				const assistantMessage = mapChatMessageReadToMessage(
					response.assistant_message,
				)

				const mappedSources = mapResponseSources(response.sources)
				const fullContent = assistantMessage.content
				const words = fullContent.trim().length > 0 ? fullContent.split(/\s+/) : []

				const streamingAssistant: Message = {
					...assistantMessage,
					content: '',
					sources: mappedSources,
					isStreaming: true,
				}

				setMessages((prev) => [...prev, userMessage, streamingAssistant])

				if (words.length === 0) {
					setMessages((prev) =>
						prev.map((message) =>
							message.id === streamingAssistant.id
								? {
										...message,
										content: fullContent,
										isStreaming: false,
									}
								: message,
						),
					)
					setIsSending(false)
					return { chat_title: response.chat_title }
				}

				setIsStreaming(true)
				streamingMessageIdRef.current = streamingAssistant.id
				streamingFinalContentRef.current = fullContent

				let index = 0
				streamTimerRef.current = setInterval(() => {
					index += 1

					const partial = words.slice(0, index).join(' ')
					setMessages((prev) =>
						prev.map((message) =>
							message.id === streamingAssistant.id
								? {
										...message,
										content: partial,
										isStreaming: index < words.length,
									}
								: message,
						),
					)

					if (index >= words.length) {
						// Finalize the simulated stream and then sync with server
						if (streamTimerRef.current) {
							clearInterval(streamTimerRef.current)
							streamTimerRef.current = null
						}
						// Mark the message completed locally
						setMessages((prev) =>
							prev.map((message) =>
								message.id === streamingAssistant.id
									? { ...message, content: streamingFinalContentRef.current, isStreaming: false }
									: message,
							),
						)
						streamingMessageIdRef.current = null
						streamingFinalContentRef.current = ''
						setIsStreaming(false)
						// Sync final persisted state from server (includes saved sources)
						;(async () => {
							try {
								await loadHistory(chatId)
							} catch {
								// Non-fatal; keep local state if refresh fails.
							} finally {
								setIsSending(false)
							}
						})()
						return
					}
				}, STREAM_MS_PER_WORD)

				return { chat_title: response.chat_title }
			} finally {
				// leave isSending to be cleared when streaming completes or when
				// the zero-word branch handles it.
			}
		},
		[stopStreaming],
	)

	const clearMessages = useCallback(() => {
		stopStreaming()
		setMessages([])
	}, [stopStreaming])

	return {
		messages,
		isLoadingHistory,
		isSending,
		isStreaming,
		loadHistory,
		sendMessage,
		stopStreaming,
		clearMessages,
	}
}
