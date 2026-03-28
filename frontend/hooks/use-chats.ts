'use client'

import { useCallback, useEffect, useState } from 'react'

import { createChat as createChatApi, listChats, deleteChat as deleteChatApi, updateChat as updateChatApi } from '@/lib/api/chats'
import type { ChatSession } from '@/lib/types'
import { useAuth } from '@/hooks/use-auth'

type UseChatsResult = {
	chats: ChatSession[]
	isLoading: boolean
	createChat: (title?: string, firstMessage?: string) => Promise<ChatSession>
	deleteChat: (id: string) => void
	updateChatTitle: (id: string, title: string) => void
	refreshChats: () => Promise<void>
}

export const useChats = (): UseChatsResult => {
	const { user } = useAuth()
	const [chats, setChats] = useState<ChatSession[]>([])
	const [isLoading, setIsLoading] = useState(true)

	const refreshChats = useCallback(async () => {
		setIsLoading(true)
		try {
			const sessions = await listChats()
			setChats(
				[...sessions].sort(
					(a, b) =>
						new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
				),
			)
		} catch {
			setChats([])
		} finally {
			setIsLoading(false)
		}
	}, [])

	useEffect(() => {
		void refreshChats().catch(() => {
			// Errors are handled within refreshChats.
		})
	}, [refreshChats])

	const createChat = useCallback(
		async (title?: string, firstMessage?: string) => {
			if (!user?.id) {
				throw new Error('Cannot create chat without authenticated user')
			}

			const session = await createChatApi(user.id, title, firstMessage)

			setChats((prev) => {
				const next = [session, ...prev]
				return next.sort(
					(a, b) =>
						new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
				)
			})

			// Keep user ownership in state even if API omits fields in future changes.
			return session
		},
		[user?.id],
	)

	const deleteChat = useCallback((id: string) => {
		// Optimistic update
		setChats((prev) => prev.filter((chat) => chat.id !== id))

		// Fire-and-forget backend delete; errors are non-fatal for optimistic UX.
		void deleteChatApi(id).catch(() => {
			// On error, refresh the list to reconcile state
			void refreshChats()
		})
	}, [refreshChats])

	const updateChatTitle = useCallback((id: string, title: string) => {
		// Optimistic update
		setChats((prev) => prev.map((c) => c.id === id ? { ...c, title } : c))

		void updateChatApi(id, { title }).catch(() => {
			// On error, refresh to reconcile
			void refreshChats()
		})
	}, [refreshChats])

	return {
		chats,
		isLoading,
		createChat,
		deleteChat,
		updateChatTitle,
		refreshChats,
	}
}
