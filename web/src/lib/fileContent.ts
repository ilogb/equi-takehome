import { useQuery } from '@tanstack/react-query'
import { ApiError, urls } from '@/lib/api'

async function fetchContent(fileId: number, as: 'buffer' | 'text' | 'probe'): Promise<ArrayBuffer | string | null> {
  const res = await fetch(urls.fileContent(fileId), { credentials: 'same-origin' })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = (await res.json()) as { detail?: unknown }
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      /* keep statusText */
    }
    throw new ApiError(res.status, detail)
  }
  if (as === 'probe') {
    void res.body?.cancel()
    return null
  }
  return as === 'buffer' ? res.arrayBuffer() : res.text()
}

export function useContent(fileId: number, as: 'buffer' | 'text' | 'probe', enabled: boolean) {
  return useQuery({
    queryKey: ['file-content', fileId, as],
    queryFn: () => fetchContent(fileId, as),
    enabled,
    retry: false,
    staleTime: Infinity,
  })
}

