'use client'

import { useEffect } from 'react'
import { usePathname, useRouter } from 'next/navigation'

import { AppErrorBoundary } from '@/components/app/error-boundary'
import { Toaster } from '@/components/ui/sonner'
import { useAuth } from '@/hooks/use-auth'

export default function AppLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const router = useRouter()
  const pathname = usePathname()
  const { token, user, isLoading } = useAuth()

  useEffect(() => {
    if (isLoading) {
      return
    }

    if (!token || !user) {
      const next = pathname ? `?next=${encodeURIComponent(pathname)}` : ''
      router.replace(`/login${next}`)
    }
  }, [isLoading, pathname, router, token, user])

  if (isLoading || !token || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <p className="text-sm text-muted-foreground">Validating session...</p>
      </div>
    )
  }

  return (
    <AppErrorBoundary>
      {children}
      <Toaster richColors closeButton />
    </AppErrorBoundary>
  )
}
