import type { ChatMessageRead } from "@/lib/types"
import { apiRequest } from "./client"

export interface SendMessageResponse {
	user_message: ChatMessageRead
	assistant_message: ChatMessageRead
	sources: Array<Record<string, unknown>>
	chat_title?: string | null
}

export const sendMessage = async (
	chatId: string,
	content: string
) => {
	return apiRequest<SendMessageResponse>("/api/messages/send", {
		method: "POST",
		body: JSON.stringify({
			chat_id: chatId,
			content,
			use_rag: true,
		}),
	})
}

export const getChatHistory = async (chatId: string) => {
	return apiRequest<ChatMessageRead[]>(`/api/messages/${chatId}/history`)
}
