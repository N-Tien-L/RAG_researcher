'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import {
	addYoutube as addYoutubeApi,
	getSource,
	listSources,
	processSource,
	uploadPdf as uploadPdfApi,
} from '@/lib/api/sources'
import type { Source } from '@/lib/types'

const POLL_INTERVAL_MS = 3000
const POLL_MAX_INTERVAL_MS = 12000
const POLL_TIMEOUT_MS = 15 * 60 * 1000

type UseSourcesResult = {
	sources: Source[]
	isLoading: boolean
	processingSourceIds: Set<string>
	uploadPdf: (
		file: File,
		title?: string,
	) => Promise<Source>
	addYoutube: (
		url: string,
		title?: string,
	) => Promise<Source>
	refreshSources: () => Promise<void>
}

const sortSourcesByCreatedAt = (items: Source[]) => {
	return [...items].sort(
		(a, b) =>
			new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
	)
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

export const useSources = (activeChatId?: string | null): UseSourcesResult => {
	const isUnmountedRef = useRef(false)
	const [sources, setSources] = useState<Source[]>([])
	const [isLoading, setIsLoading] = useState(true)
	const [processingSourceIds, setProcessingSourceIds] = useState<Set<string>>(
		new Set(),
	)

	const markProcessing = useCallback((sourceId: string, isProcessing: boolean) => {
		setProcessingSourceIds((prev) => {
			const next = new Set(prev)
			if (isProcessing) {
				next.add(sourceId)
			} else {
				next.delete(sourceId)
			}
			return next
		})
	}, [])

	const upsertSource = useCallback((incoming: Source) => {
		if (isUnmountedRef.current) {
			return
		}

		setSources((prev) => {
			const next = prev.filter((item) => item.id !== incoming.id)
			next.push(incoming)
			return sortSourcesByCreatedAt(next)
		})
	}, [])

	const refreshSources = useCallback(async () => {
		setIsLoading(true)
		try {
			const result = await listSources()
			if (isUnmountedRef.current) {
				return
			}

			setSources(sortSourcesByCreatedAt(result))
		} catch {
			if (!isUnmountedRef.current) {
				setSources([])
			}
		} finally {
			if (!isUnmountedRef.current) {
				setIsLoading(false)
			}
		}
	}, [])

	const pollUntilSettled = useCallback(
		async (sourceId: string, fallbackSource: Source) => {
			const deadline = Date.now() + POLL_TIMEOUT_MS
			let waitMs = POLL_INTERVAL_MS
			let latestKnown = fallbackSource

			while (!isUnmountedRef.current && Date.now() < deadline) {
				try {
					const latest = await getSource(sourceId)
					latestKnown = latest
					upsertSource(latest)

					if (latest.status !== 'processing') {
						return latest
					}
				} catch {
					if (latestKnown.status !== 'processing') {
						return latestKnown
					}
				}

				await sleep(waitMs)
				waitMs = Math.min(waitMs * 2, POLL_MAX_INTERVAL_MS)
			}

			return latestKnown
		},
		[upsertSource],
	)

	const uploadPdf = useCallback(
		async (file: File, title?: string) => {
			const created = await uploadPdfApi(file, title, activeChatId)
			upsertSource(created)
			markProcessing(created.id, true)

			try {
				try {
					await processSource(created.id)
				} catch {
					const latest = await getSource(created.id)
					upsertSource(latest)
					if (latest.status === 'failed') {
						return latest
					}
				}

				const settled = await pollUntilSettled(created.id, created)
				return settled
			} finally {
				markProcessing(created.id, false)
			}
		},
		[activeChatId, markProcessing, pollUntilSettled, upsertSource],
	)

	const addYoutube = useCallback(
		async (url: string, title?: string) => {
			const created = await addYoutubeApi(url, title, activeChatId)
			upsertSource(created)
			markProcessing(created.id, true)

			try {
				try {
					await processSource(created.id)
				} catch {
					const latest = await getSource(created.id)
					upsertSource(latest)
					if (latest.status === 'failed') {
						return latest
					}
				}

				const settled = await pollUntilSettled(created.id, created)
				return settled
			} finally {
				markProcessing(created.id, false)
			}
		},
		[activeChatId, markProcessing, pollUntilSettled, upsertSource],
	)

	useEffect(() => {
		void refreshSources().catch(() => {
			// Errors are handled within refreshSources.
		})
	}, [refreshSources])

	useEffect(() => {
		return () => {
			isUnmountedRef.current = true
		}
	}, [])

	return useMemo(
		() => ({
			sources,
			isLoading,
			processingSourceIds,
			uploadPdf,
			addYoutube,
			refreshSources,
		}),
		[
			sources,
			isLoading,
			processingSourceIds,
			uploadPdf,
			addYoutube,
			refreshSources,
		],
	)
}
