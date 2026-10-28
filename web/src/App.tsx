import { Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { AppHeader } from '@/components/AppHeader'
import { ApiError, useMe } from '@/lib/api'
import { ConnectPage } from '@/pages/ConnectPage'
import { DataPage, DocumentPage, LibraryPage, SearchPage } from '@/pages/Stub'

/** Shell for signed-in screens. A 401 from /api/auth/me sends the user to /connect. */
export function RequireAuth() {
  const me = useMe()
  if (me.error instanceof ApiError && me.error.status === 401) return <Navigate to="/connect" replace />
  if (me.isPending) return <p className="p-8 text-sm text-muted-foreground">Loading…</p>
  if (me.isError) return <p role="alert" className="p-8 text-sm text-negative">Could not reach the server.</p>
  return (
    <>
      <AppHeader />
      <main>
        <Outlet />
      </main>
    </>
  )
}

export default function App() {
  return (
    <Routes>
      <Route path="/connect" element={<ConnectPage />} />
      <Route element={<RequireAuth />}>
        <Route path="/library" element={<LibraryPage />} />
        <Route path="/documents/:id" element={<DocumentPage />} />
        <Route path="/data" element={<DataPage />} />
        <Route path="/search" element={<SearchPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/library" replace />} />
    </Routes>
  )
}
