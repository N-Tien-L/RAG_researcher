'use client'

import { useCallback, useEffect, useState } from 'react'

import { getMe, login as loginApi } from '@/lib/api/auth'
import {
	ApiError,
	clearStoredToken,
	getStoredToken,
	setStoredToken,
} from '@/lib/api/client'
import type { User } from '@/lib/types'

type LoginCredentials = {
	email: string
	password: string
}

type UseAuthResult = {
	user: User | null
	token: string | null
	login: (credentials: LoginCredentials) => Promise<User>
	logout: () => void
	isLoading: boolean
}

export const useAuth = (): UseAuthResult => {
	const [user, setUser] = useState<User | null>(null)
	const [token, setToken] = useState<string | null>(null)
	const [isLoading, setIsLoading] = useState(true)

	const logout = useCallback(() => {
		clearStoredToken()
		setToken(null)
		setUser(null)

		if (typeof window !== 'undefined' && window.location.pathname !== '/login') {
			window.location.assign('/login')
		}
	}, [])

	const login = useCallback(
		async ({ email, password }: LoginCredentials) => {
			const tokenResponse = await loginApi(email, password)
			setStoredToken(tokenResponse.access_token)
			setToken(tokenResponse.access_token)

			const me = await getMe()
			setUser(me)
			return me
		},
		[]
	)

	useEffect(() => {
		let isCancelled = false

		const hydrateAuth = async () => {
			const storedToken = getStoredToken()

			if (!storedToken) {
				if (!isCancelled) {
					setIsLoading(false)
				}
				return
			}

			if (!isCancelled) {
				setToken(storedToken)
			}

			try {
				const me = await getMe()
				if (!isCancelled) {
					setUser(me)
				}
			} catch (error) {
				if (error instanceof ApiError && error.status === 401) {
					clearStoredToken()
					if (!isCancelled) {
						setToken(null)
						setUser(null)
					}
					return
				}

				if (!isCancelled) {
					setUser(null)
				}
			} finally {
				if (!isCancelled) {
					setIsLoading(false)
				}
			}
		}

		void hydrateAuth()

		return () => {
			isCancelled = true
		}
	}, [])

	return {
		user,
		token,
		login,
		logout,
		isLoading,
	}
}
