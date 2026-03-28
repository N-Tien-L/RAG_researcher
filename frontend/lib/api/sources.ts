import type { Source } from "@/lib/types"
import { apiRequest } from "./client"

export interface SourceProcessResponse {
	source: Source
	chunks_added: number
	ids: string[]
	content_hash: string
	status: "ingested" | "skipped"
}

export const listSources = async () => {
	return apiRequest<Source[]>("/api/sources/")
}

export const getSource = async (sourceId: string) => {
	return apiRequest<Source>(`/api/sources/${sourceId}`)
}

export const uploadPdf = async (
	file: File,
	title?: string,
	chatSessionId?: string | null,
) => {
	const formData = new FormData()
	formData.append("file", file)
	if (title?.trim()) {
		formData.append("title", title.trim())
	}
	if (chatSessionId) {
		formData.append("chat_session_id", chatSessionId)
	}
	return apiRequest<Source>("/api/sources/upload", {
		method: "POST",
		body: formData,
	})
}

export const addYoutube = async (
	url: string,
	title?: string,
	chatSessionId?: string | null,
) => {
	const body = new URLSearchParams()
	body.set("url", url)
	if (title?.trim()) {
		body.set("title", title.trim())
	}
	if (chatSessionId) {
		body.set("chat_session_id", chatSessionId)
	}
	return apiRequest<Source>("/api/sources/youtube", {
		method: "POST",
		headers: {
			"Content-Type": "application/x-www-form-urlencoded",
		},
		body,
	})
}

export const processSource = async (sourceId: string) => {
	return apiRequest<SourceProcessResponse>(`/api/sources/${sourceId}/process`, {
		method: "POST",
	})
}
