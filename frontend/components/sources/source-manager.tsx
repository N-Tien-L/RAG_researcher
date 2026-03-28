'use client'

import { type ChangeEvent, type DragEvent, useEffect, useMemo, useState } from 'react'

import { getChatSources, linkSourceToChat } from '@/lib/api/chats'
import { ApiError } from '@/lib/api/client'
import type { Source } from '@/lib/types'
import { useSources } from '@/hooks/use-sources'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Spinner } from '@/components/ui/spinner'

interface SourceManagerProps {
	activeChatId: string | null
}

const formatApiError = (error: unknown) => {
	const typed = error as ApiError
	if (typed && typeof typed.message === 'string' && typed.message.length > 0) {
		return typed.message
	}
	return 'Request failed. Please try again.'
}

const sourceTypeIcon = (type: Source['type']) => {
	if (type === 'youtube') {
		return '▶'
	}
	return '📄'
}

const statusBadge = (source: Source, isProcessing: boolean) => {
	if (source.status === 'ready') {
		return (
			<Badge variant="outline" className="gap-1 border-emerald-200 text-emerald-700">
				<span className="h-2 w-2 rounded-full bg-emerald-500" aria-hidden />
				ready
			</Badge>
		)
	}

	if (source.status === 'failed') {
		return (
			<Badge variant="outline" className="gap-1 border-rose-200 text-rose-700">
				<span className="h-2 w-2 rounded-full bg-rose-500" aria-hidden />
				failed
			</Badge>
		)
	}

	return (
		<Badge variant="outline" className="gap-1 border-amber-200 text-amber-700">
			{isProcessing ? <Spinner className="size-3" /> : <span className="h-2 w-2 rounded-full bg-amber-500" aria-hidden />}
			processing
		</Badge>
	)
}

export function SourceManager({ activeChatId }: SourceManagerProps) {
	const { sources, isLoading, processingSourceIds, uploadPdf, addYoutube, refreshSources } =
		useSources(activeChatId)

	const [dragActive, setDragActive] = useState(false)
	const [selectedFile, setSelectedFile] = useState<File | null>(null)
	const [pdfTitle, setPdfTitle] = useState('')
	const [isUploadingPdf, setIsUploadingPdf] = useState(false)

	const [youtubeUrl, setYoutubeUrl] = useState('')
	const [youtubeTitle, setYoutubeTitle] = useState('')
	const [isAddingYoutube, setIsAddingYoutube] = useState(false)

	const [linkedSourceIds, setLinkedSourceIds] = useState<Set<string>>(new Set())
	const [linkingSourceIds, setLinkingSourceIds] = useState<Set<string>>(new Set())

	useEffect(() => {
		if (!activeChatId) {
			setLinkedSourceIds(new Set())
			return
		}

		let cancelled = false
		void getChatSources(activeChatId)
			.then((linkedSources) => {
				if (cancelled) {
					return
				}
				setLinkedSourceIds(new Set(linkedSources.map((source) => source.id)))
			})
			.catch(() => {
				if (!cancelled) {
					setLinkedSourceIds(new Set())
				}
			})

		return () => {
			cancelled = true
		}
	}, [activeChatId])

	const sortedSources = useMemo(() => {
		return [...sources].sort(
			(a, b) =>
				new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
		)
	}, [sources])

	const beginLinking = (sourceId: string) => {
		setLinkingSourceIds((prev) => {
			const next = new Set(prev)
			next.add(sourceId)
			return next
		})
	}

	const endLinking = (sourceId: string) => {
		setLinkingSourceIds((prev) => {
			const next = new Set(prev)
			next.delete(sourceId)
			return next
		})
	}

	const handleUploadPdf = async () => {
		if (!selectedFile) {
			toast.error('Select or drop a valid PDF file to continue.')
			return
		}

		setIsUploadingPdf(true)
		try {
			const title = pdfTitle.trim() || selectedFile.name
			await uploadPdf(selectedFile, title)
			setSelectedFile(null)
			setPdfTitle('')
			toast.success('PDF uploaded. Processing started.')
		} catch (error) {
			if (!(error instanceof ApiError && error.notified)) {
				toast.error(formatApiError(error))
			}
		} finally {
			setIsUploadingPdf(false)
		}
	}

	const handleAddYoutube = async () => {
		if (!youtubeUrl.trim()) {
			toast.error('Provide a YouTube URL before adding.')
			return
		}

		setIsAddingYoutube(true)
		try {
			await addYoutube(youtubeUrl.trim(), youtubeTitle.trim() || undefined)
			setYoutubeUrl('')
			setYoutubeTitle('')
			toast.success('YouTube source added. Processing started.')
		} catch (error) {
			if (!(error instanceof ApiError && error.notified)) {
				toast.error(formatApiError(error))
			}
		} finally {
			setIsAddingYoutube(false)
		}
	}

	const handleFileDrop = (event: DragEvent<HTMLLabelElement>) => {
		event.preventDefault()
		setDragActive(false)

		const file = event.dataTransfer.files?.[0]
		if (!file) {
			return
		}

		if (file.type !== 'application/pdf') {
			toast.error('Only PDF files are supported.')
			return
		}

		setSelectedFile(file)
		if (!pdfTitle) {
			setPdfTitle(file.name)
		}
	}

	const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
		const file = event.target.files?.[0]
		if (!file) {
			return
		}

		if (file.type !== 'application/pdf') {
			toast.error('Only PDF files are supported.')
			return
		}

		setSelectedFile(file)
		if (!pdfTitle) {
			setPdfTitle(file.name)
		}
	}

	const handleLinkToChat = async (sourceId: string, checked: boolean) => {
		if (!checked || !activeChatId) {
			return
		}

		beginLinking(sourceId)
		try {
			await linkSourceToChat(activeChatId, sourceId)
			setLinkedSourceIds((prev) => {
				const next = new Set(prev)
				next.add(sourceId)
				return next
			})
			toast.success('Source linked to chat')
		} catch (error) {
			if (!(error instanceof ApiError && error.notified)) {
				toast.error(formatApiError(error))
			}
		} finally {
			endLinking(sourceId)
		}
	}

	return (
		<div className="flex h-full flex-col">
			<div className="border-b px-6 py-5">
				<h2 className="text-lg font-semibold">Manage Sources</h2>
				<p className="text-sm text-muted-foreground">
					Upload PDFs, add YouTube videos, and attach ready sources to this chat.
				</p>
			</div>

			<ScrollArea className="min-h-0 flex-1 px-6 py-4">
				<div className="space-y-6">
					<section className="space-y-3">
						<h3 className="text-sm font-semibold">Upload PDF</h3>
						<label
							onDragOver={(event) => {
								event.preventDefault()
								setDragActive(true)
							}}
							onDragLeave={() => setDragActive(false)}
							onDrop={handleFileDrop}
							className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed p-6 text-center ${
								dragActive
									? 'border-primary bg-primary/5'
									: 'border-border bg-muted/20 hover:bg-muted/30'
							}`}
						>
							<input
								type="file"
								accept="application/pdf"
								onChange={handleFileChange}
								className="hidden"
							/>
							<p className="text-sm font-medium">Drop PDF here or click to browse</p>
							<p className="text-xs text-muted-foreground">
								{selectedFile ? `Selected: ${selectedFile.name}` : 'PDF only'}
							</p>
						</label>

						<Input
							placeholder="Title (optional)"
							value={pdfTitle}
							onChange={(event) => setPdfTitle(event.target.value)}
						/>
						<Button
							type="button"
							onClick={handleUploadPdf}
							disabled={isUploadingPdf}
							className="w-full"
						>
							{isUploadingPdf ? (
								<>
									<Spinner className="mr-2" /> Uploading and processing...
								</>
							) : (
								'Upload and process PDF'
							)}
						</Button>
					</section>

					<section className="space-y-3">
						<h3 className="text-sm font-semibold">Add YouTube</h3>
						<Input
							placeholder="https://www.youtube.com/watch?v=..."
							value={youtubeUrl}
							onChange={(event) => setYoutubeUrl(event.target.value)}
						/>
						<Input
							placeholder="Video title"
							value={youtubeTitle}
							onChange={(event) => setYoutubeTitle(event.target.value)}
						/>
						<Button
							type="button"
							onClick={handleAddYoutube}
							disabled={isAddingYoutube}
							className="w-full"
						>
							{isAddingYoutube ? (
								<>
									<Spinner className="mr-2" /> Adding and processing...
								</>
							) : (
								'Add and process YouTube source'
							)}
						</Button>
					</section>

					<section className="space-y-3">
						<div className="flex items-center justify-between">
							<h3 className="text-sm font-semibold">Your sources</h3>
							<Button variant="ghost" size="sm" onClick={() => void refreshSources()}>
								Refresh
							</Button>
						</div>

						{isLoading ? (
							<div className="flex items-center gap-2 text-sm text-muted-foreground">
								<Spinner /> Loading sources...
							</div>
						) : sortedSources.length === 0 ? (
							<p className="text-sm text-muted-foreground">No sources yet. Upload a PDF or add a YouTube URL to get started.</p>
						) : (
							<ul className="space-y-2">
								{sortedSources.map((source) => {
									const isProcessing =
										source.status === 'processing' ||
										processingSourceIds.has(source.id)
									const isLinked = linkedSourceIds.has(source.id)
									const isLinking = linkingSourceIds.has(source.id)

									return (
										<li
											key={source.id}
											className="rounded-lg border border-border bg-card p-3"
										>
											<div className="flex items-start justify-between gap-2">
												<div className="min-w-0">
													<p className="truncate text-sm font-medium">
														{sourceTypeIcon(source.type)} {source.title}
													</p>
													<p className="text-xs text-muted-foreground">
														{source.id}
													</p>
												</div>
												{statusBadge(source, isProcessing)}
											</div>

											<div className="mt-3 flex items-center gap-2">
												<Checkbox
													id={`source-link-${source.id}`}
													checked={isLinked}
													disabled={
														source.status !== 'ready' ||
														!activeChatId ||
														isLinked ||
														isLinking
													}
													onCheckedChange={(checked) =>
														void handleLinkToChat(source.id, checked === true)
													}
												/>
												<label
													htmlFor={`source-link-${source.id}`}
													className="text-xs text-muted-foreground"
												>
													{!activeChatId
														? 'Select a chat first to link'
														: isLinked
															? 'Linked to current chat'
															: isLinking
																? 'Linking...'
																: 'Link to current chat'}
												</label>
											</div>
										</li>
									)
								})}
							</ul>
						)}
					</section>
				</div>
			</ScrollArea>
		</div>
	)
}
