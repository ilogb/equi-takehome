import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query'
import { ApiError } from './api'

/** QueryClient whose caches report any 401 (expired session mid-use) to onUnauthorized. */
export function createQueryClient(onUnauthorized: () => void, retry: boolean | number = 1): QueryClient {
  const onError = (err: unknown) => {
    if (err instanceof ApiError && err.status === 401) onUnauthorized()
  }
  return new QueryClient({
    queryCache: new QueryCache({ onError }),
    mutationCache: new MutationCache({ onError }),
    defaultOptions: { queries: { refetchOnWindowFocus: false, retry } },
  })
}
