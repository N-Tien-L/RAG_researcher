import type { User } from "@/lib/types"
import { apiRequest, setStoredToken } from "./client"

export interface TokenResponse {
	access_token: string
	token_type: string
}

export const login = async (email: string, password: string) => {
	const body = new URLSearchParams({
		username: email,
		password,
	})

	const token = await apiRequest<TokenResponse>(
		"/api/auth/login",
		{
			method: "POST",
			body,
		},
		{ auth: false }
	)

	setStoredToken(token.access_token)
	return token
}

export const register = async (
	email: string,
	username: string | undefined,
	password: string
) => {
	return apiRequest<User>(
		"/api/users/",
		{
			method: "POST",
			body: JSON.stringify({
				email,
				username: username || undefined,
				password,
			}),
		},
		{ auth: false }
	)
}

export const getMe = async () => {
	return apiRequest<User>("/api/auth/me")
}
