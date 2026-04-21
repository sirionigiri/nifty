"use client"
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useState } from 'react'

export function QueryProvider({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 1000 * 60 * 5, // Keep data "fresh" for 5 minutes
        gcTime: 1000 * 60 * 30,    // Keep in cache for 30 minutes
        refetchOnWindowFocus: false, // Stop refreshing when you switch browser tabs
      },
    },
  }))

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
}