import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query'
import { ApiError } from './api'

/** QueryClient whose caches report any 401 (expired session mid-use) to onUnauthorized. */
export function createQueryClient(onUnauthorized: () => void, retry: boolean | number = 1): QueryClient {
  // A query tagged meta.handles401 (the /connect screen) reads a 401 as "signed out", not "session expired".
  const onError = (err: unknown, query?: { meta?: Record<string, unknown> }) => {
    if (query?.meta?.handles401) return
    if (err instanceof ApiError && err.status === 401) onUnauthorized()
  }
  return new QueryClient({
    queryCache: new QueryCache({ onError: (err, query) => onError(err, query) }),
    mutationCache: new MutationCache({ onError: (err) => onError(err) }),
    defaultOptions: { queries: { refetchOnWindowFocus: false, retry } },
  })
}
