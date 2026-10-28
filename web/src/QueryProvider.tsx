import { QueryClientProvider } from '@tanstack/react-query'
import { useRef, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { createQueryClient } from '@/lib/queryClient'

/** Must sit inside the Router: a 401 anywhere clears the cache and redirects to /connect. */
export function QueryProvider({ children, retry }: { children: ReactNode; retry?: boolean | number }) {
  const navigate = useNavigate()
  const navRef = useRef(navigate)
  navRef.current = navigate
  const [client] = useState(() =>
    createQueryClient(() => {
      client.clear()
      navRef.current('/connect', { replace: true })
    }, retry),
  )
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}
