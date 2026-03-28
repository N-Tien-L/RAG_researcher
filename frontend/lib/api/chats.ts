import type { ChatSession } from "@/lib/types"
import type { Source } from "@/lib/types"
import { apiRequest } from "./client"

export const listChats = async () => {
	return apiRequest<ChatSession[]>("/api/chats/")
}

export const createChat = async (
	userId: string,
	title?: string,
	firstMessage?: string,
	collections?: string[]
) => {
	return apiRequest<ChatSession>("/api/chats/", {
		method: "POST",
		body: JSON.stringify({
			user_id: userId,
			title: title ?? undefined,
			first_message: firstMessage ?? undefined,
			collections: collections ?? [],
		}),
	})
}

export const getChat = async (id: string) => {
	return apiRequest<ChatSession>(`/api/chats/${id}`)
}

export const updateChat = async (id: string, payload: { title?: string; collections?: string[] }) => {
	return apiRequest<ChatSession>(`/api/chats/${id}`, {
		method: "PATCH",
		body: JSON.stringify(payload),
	})
}

export const deleteChat = async (id: string) => {
	return apiRequest<void>(`/api/chats/${id}`, {
		method: "DELETE",
	})
}

export interface ChatSessionSourceLink {
	chat_session_id: string
	source_id: string
	created_at: string
}

export const linkSourceToChat = async (chatId: string, sourceId: string) => {
	return apiRequest<ChatSessionSourceLink>(
		`/api/chats/${chatId}/sources/${sourceId}`,
		{
			method: "POST",
		}
	)
}

export const getChatSources = async (chatId: string) => {
	return apiRequest<Source[]>(`/api/chats/${chatId}/sources`)
}
