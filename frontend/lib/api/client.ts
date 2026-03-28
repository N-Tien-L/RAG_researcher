const DEFAULT_API_URL = "http://localhost:8000"
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? DEFAULT_API_URL
const TOKEN_STORAGE_KEY = "rag_token"
const LEGACY_TOKEN_STORAGE_KEY = "rag_researcher_token"

export class ApiError extends Error {
	status: number
	details?: unknown
	retryAfterSeconds?: number
	notified: boolean

	constructor(
		message: string,
		status: number,
		details?: unknown,
		retryAfterSeconds?: number
	) {
		super(message)
		this.name = "ApiError"
		this.status = status
		this.details = details
		this.retryAfterSeconds = retryAfterSeconds
		this.notified = false
	}
}

type ApiRequestOptions = {
	auth?: boolean
}

const isBrowser = () => typeof window !== "undefined"

export const getApiUrl = (path: string) => {
	if (path.startsWith("http://") || path.startsWith("https://")) {
		return path
	}

	const normalized = path.startsWith("/") ? path : `/${path}`
	return `${API_URL}${normalized}`
}

export const getStoredToken = () => {
	if (!isBrowser()) {
		return null
	}

	try {
		const token = localStorage.getItem(TOKEN_STORAGE_KEY)
		if (token) {
			return token
		}

		// Backward compatibility for previously stored token key.
		const legacyToken = localStorage.getItem(LEGACY_TOKEN_STORAGE_KEY)
		if (legacyToken) {
			localStorage.setItem(TOKEN_STORAGE_KEY, legacyToken)
			localStorage.removeItem(LEGACY_TOKEN_STORAGE_KEY)
			return legacyToken
		}

		return null
	} catch {
		return null
	}
}

export const setStoredToken = (token: string) => {
	if (!isBrowser()) {
		return
	}

	try {
		localStorage.setItem(TOKEN_STORAGE_KEY, token)
	} catch {
		// Ignore storage failures (private mode, quota exceeded, etc.).
	}
}

export const clearStoredToken = () => {
	if (!isBrowser()) {
		return
	}

	try {
		localStorage.removeItem(TOKEN_STORAGE_KEY)
		localStorage.removeItem(LEGACY_TOKEN_STORAGE_KEY)
	} catch {
		// Ignore storage failures.
	}
}

const redirectToLogin = () => {
	if (!isBrowser()) {
		return
	}

	if (window.location.pathname !== "/login") {
		window.location.assign("/login")
	}
}

const readErrorMessage = async (response: Response) => {
	const contentType = response.headers.get("content-type") ?? ""

	if (contentType.includes("application/json")) {
		const body = await response.json().catch(() => null)
		if (body && typeof body === "object" && "detail" in body) {
			return { message: String(body.detail ?? response.statusText), details: body }
		}
		return { message: response.statusText, details: body }
	}

	const text = await response.text().catch(() => "")
	return { message: text || response.statusText, details: text || undefined }
}

const parseRetryAfterHeader = (value: string | null) => {
	if (!value) {
		return undefined
	}

	const seconds = Number(value)
	if (Number.isFinite(seconds) && seconds >= 0) {
		return Math.ceil(seconds)
	}

	const asDate = Date.parse(value)
	if (!Number.isNaN(asDate)) {
		return Math.max(0, Math.ceil((asDate - Date.now()) / 1000))
	}

	return undefined
}

const getApiErrorMessage = (error: ApiError) => {
	if (error.status === 503) {
		return "AI service is temporarily unavailable. Please try again."
	}

	if (error.status === 429) {
		if (typeof error.retryAfterSeconds === "number") {
			return `Rate limit reached. Please wait ${error.retryAfterSeconds} seconds.`
		}

		return "Rate limit reached. Please wait a moment and try again."
	}

	return error.message || "Request failed. Please try again."
}

const notifyApiError = async (error: ApiError) => {
	if (!isBrowser()) {
		return
	}

	const { toast } = await import("sonner")
	toast.error(getApiErrorMessage(error))
	error.notified = true
}

export const apiRequest = async <T>(
	path: string,
	init: RequestInit = {},
	options: ApiRequestOptions = {}
): Promise<T> => {
	const url = getApiUrl(path)
	const headers = new Headers(init.headers)

	headers.set("Accept", "application/json")

	if (options.auth !== false) {
		const token = getStoredToken()
		if (token) {
			headers.set("Authorization", `Bearer ${token}`)
		}
	}

	if (
		init.body &&
		!(init.body instanceof FormData) &&
		!(init.body instanceof URLSearchParams) &&
		!headers.has("Content-Type")
	) {
		headers.set("Content-Type", "application/json")
	}

	const response = await fetch(url, {
		...init,
		headers,
	})

	if (response.status === 401) {
		clearStoredToken()
		redirectToLogin()
	}

	if (!response.ok) {
		const { message, details } = await readErrorMessage(response)
		const retryAfterSeconds = parseRetryAfterHeader(
			response.headers.get("Retry-After")
		)
		const apiError = new ApiError(
			message,
			response.status,
			details,
			retryAfterSeconds
		)
		await notifyApiError(apiError)
		throw apiError
	}

	if (response.status === 204) {
		return undefined as T
	}

	const contentType = response.headers.get("content-type") ?? ""
	if (contentType.includes("application/json")) {
		return (await response.json()) as T
	}

	return (await response.text()) as unknown as T
}
