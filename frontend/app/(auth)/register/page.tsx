'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { FormEvent, useState } from 'react'

import { Button } from '@/components/ui/button'
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuth } from '@/hooks/use-auth'
import { register } from '@/lib/api/auth'
import { ApiError } from '@/lib/api/client'

export default function RegisterPage() {
	const router = useRouter()
	const { login } = useAuth()

	const [email, setEmail] = useState('')
	const [username, setUsername] = useState('')
	const [password, setPassword] = useState('')
	const [errorMessage, setErrorMessage] = useState<string | null>(null)
	const [isSubmitting, setIsSubmitting] = useState(false)

	const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
		event.preventDefault()
		setErrorMessage(null)
		setIsSubmitting(true)

		try {
			await register(email, username.trim() || undefined, password)
			await login({ email, password })
			router.replace('/')
		} catch (error) {
			if (error instanceof ApiError && error.status === 409) {
				setErrorMessage(
					'Email or username is already in use. Please choose different credentials.'
				)
			} else {
				setErrorMessage('Registration failed. Please try again in a moment.')
			}
		} finally {
			setIsSubmitting(false)
		}
	}

	return (
		<div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-background px-4 py-10">
			<div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_right,oklch(0.92_0.05_215)_0,transparent_45%),radial-gradient(circle_at_bottom_left,oklch(0.96_0.03_180)_0,transparent_45%)]" />
			<Card className="relative z-10 w-full max-w-md backdrop-blur-sm">
				<CardHeader>
					<CardTitle>Create account</CardTitle>
					<CardDescription>
						Start a new RAG researcher workspace in under a minute.
					</CardDescription>
					<div className="mt-2 grid grid-cols-2 gap-2">
						<Button asChild variant="outline" size="sm">
							<Link href="/login">Sign In</Link>
						</Button>
						<Button asChild variant="default" size="sm">
							<Link href="/register">Register</Link>
						</Button>
					</div>
				</CardHeader>
				<CardContent>
					<form className="space-y-4" onSubmit={handleSubmit}>
						<div className="space-y-2">
							<Label htmlFor="email">Email</Label>
							<Input
								id="email"
								type="email"
								autoComplete="email"
								value={email}
								onChange={(event) => setEmail(event.target.value)}
								required
							/>
						</div>
						<div className="space-y-2">
							<Label htmlFor="username">Username (optional)</Label>
							<Input
								id="username"
								type="text"
								autoComplete="username"
								value={username}
								onChange={(event) => setUsername(event.target.value)}
							/>
						</div>
						<div className="space-y-2">
							<Label htmlFor="password">Password</Label>
							<Input
								id="password"
								type="password"
								autoComplete="new-password"
								value={password}
								onChange={(event) => setPassword(event.target.value)}
								required
							/>
						</div>

						{errorMessage ? (
							<p className="text-sm text-destructive" role="alert">
								{errorMessage}
							</p>
						) : null}

						<Button className="w-full" disabled={isSubmitting} type="submit">
							{isSubmitting ? 'Creating account...' : 'Create account'}
						</Button>
					</form>
				</CardContent>
			</Card>
		</div>
	)
}
