import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'

/** Default handlers: an authenticated user with a folder. Tests override per case with server.use(). */
export const handlers = [
  http.get('/api/auth/me', () =>
    HttpResponse.json({ email: 'imran@example.com', name: 'Imran Brown', needs_reconnect: false, has_folder: true }),
  ),
  http.get('/api/folder', () =>
    HttpResponse.json({
      name: 'Fund documents',
      last_synced_at: new Date().toISOString(),
      last_error: null,
      counts_by_status: { done: 3 },
      needs_reconnect: false,
    }),
  ),
  http.get('/api/dashboard', () =>
    HttpResponse.json({
      documents: { total: 0, done: 0, needs_review: 0, failed: 0, processing: 0 },
      figures: { total: 0, needs_review: 0, conflicts: 0 },
      entities: { funds: 0, accounts: 0 },
      one_year: [],
      aum: [],
    }),
  ),
]

export const server = setupServer(...handlers)
