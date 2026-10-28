import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { server } from '@/test/server'
import { api, ApiError, keys, urls } from './api'

describe('api client', () => {
  it('builds query strings, skipping empty values', async () => {
    let seen = ''
    server.use(
      http.get('/api/rows', ({ request }) => {
        seen = new URL(request.url).search
        return HttpResponse.json({ rows: [], total: 0 })
      }),
    )
    const page = await api.rows({ fund: 'Alpha', measure: 'return', needs_review: true, manager: '', limit: 50 })
    expect(page).toEqual({ rows: [], total: 0 })
    expect(new URLSearchParams(seen).get('fund')).toBe('Alpha')
    expect(new URLSearchParams(seen).get('needs_review')).toBe('true')
    expect(new URLSearchParams(seen).has('manager')).toBe(false)
  })

  it('throws ApiError carrying status and detail', async () => {
    server.use(http.get('/api/folder', () => HttpResponse.json({ detail: 'no folder chosen' }, { status: 404 })))
    await expect(api.folder()).rejects.toMatchObject({ name: 'ApiError', status: 404, message: 'no folder chosen' })
    await expect(api.folder()).rejects.toBeInstanceOf(ApiError)
  })

  it('posts JSON for analyze', async () => {
    let body: unknown
    server.use(
      http.post('/api/analyze', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ text: 'ok', table: null, sources: [], steps: [] })
      }),
    )
    const r = await api.analyze('what was the 1y return?')
    expect(body).toEqual({ question: 'what was the 1y return?' })
    expect(r.table).toBeNull()
  })

  it('keys include their filters; urls are direct links', () => {
    expect(keys.files({ status: 'failed' })).toEqual(['files', { status: 'failed' }])
    expect(keys.rows({ fund: 'x' })).toEqual(['rows', { fund: 'x' }])
    expect(urls.fileContent(7)).toBe('/api/files/7/content')
    expect(urls.rowsCsv({ fund: 'x', limit: 10 })).toBe('/api/rows.csv?fund=x')
  })
})
