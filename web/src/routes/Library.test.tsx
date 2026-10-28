import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { QueryProvider } from '@/QueryProvider'
import { server } from '@/test/server'
import { Library } from './Library'

const NOW = new Date('2026-10-28T10:50:00Z')

const file = (over: object = {}) => ({
  id: 1,
  name: 'fundsmith_factsheet_2026-08.pdf',
  path: 'Factsheets/fundsmith_factsheet_2026-08.pdf',
  mime_type: 'application/pdf',
  kind: 'pdf',
  status: 'done',
  error: null,
  missing_in_drive: false,
  doc_type: 'Factsheet',
  manager: 'Fundsmith',
  funds: ['Fundsmith Equity Fund'],
  as_of_date: '2026-08-31',
  tags: ['global equity', 'quality growth'],
  row_count: 18,
  updated_at: '2026-10-28T10:42:00Z',
  ...over,
})

const folder = (counts: Record<string, number>, over: object = {}) => ({
  name: 'Fund documents',
  last_synced_at: '2026-10-28T10:49:00Z',
  last_error: null,
  counts_by_status: counts,
  needs_reconnect: false,
  ...over,
})

function Where() {
  return <div data-testid="where">{useLocation().pathname}</div>
}

function renderLibrary() {
  return render(
    <MemoryRouter initialEntries={['/library']}>
      <QueryProvider retry={false}>
        <Routes>
          <Route path="/library" element={<Library />} />
          <Route path="/documents/:id" element={<Where />} />
        </Routes>
      </QueryProvider>
    </MemoryRouter>,
  )
}

const use = (files: object[], f = folder({ done: files.length })) =>
  server.use(
    http.get('/api/files', ({ request }) => {
      const status = new URL(request.url).searchParams.get('status')
      return HttpResponse.json(status ? (files as { status: string }[]).filter((r) => r.status === status) : files)
    }),
    http.get('/api/folder', () => HttpResponse.json(f)),
  )

afterEach(() => vi.useRealTimers())

describe('L1 default', () => {
  it('shows icon, path, type, manager, funds, as-of, tags, status and relative time', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true, now: NOW })
    use([
      file(),
      file({ id: 2, name: 'scan.pdf', path: 'scan.pdf', status: 'scanned_no_text', doc_type: null, manager: null, funds: [], tags: [], as_of_date: null, row_count: 0 }),
    ])
    renderLibrary()
    const row = (await screen.findByRole('link', { name: 'fundsmith_factsheet_2026-08.pdf' })).closest('tr')!
    const r = within(row)
    expect(r.getByRole('img', { name: 'PDF' })).toBeInTheDocument()
    expect(r.getByText('Factsheets')).toBeInTheDocument()
    expect(r.getByText('Factsheet')).toBeInTheDocument()
    expect(r.getByText('Fundsmith')).toBeInTheDocument()
    expect(r.getByText('Fundsmith Equity Fund')).toBeInTheDocument()
    expect(r.getByText('2026-08-31')).toBeInTheDocument()
    expect(r.getByText('global equity')).toBeInTheDocument()
    expect(r.getByText('quality growth')).toBeInTheDocument()
    expect(r.getByText('Done')).toBeInTheDocument()
    expect(r.getByText('8 min ago')).toHaveAttribute('title', expect.stringContaining('2026'))
    expect(screen.getByText('Scanned: no text', { selector: 'span' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /open folder in drive/i })).toHaveAttribute('href')
    expect(screen.getByRole('button', { name: /sync now/i })).toBeEnabled()
  })

  it('navigates to the document on row click', async () => {
    use([file({ id: 7 })])
    renderLibrary()
    await userEvent.click(await screen.findByText('Fundsmith Equity Fund'))
    expect(screen.getByTestId('where')).toHaveTextContent('/documents/7')
  })

  it('filters by status through the summary chips', async () => {
    use([file(), file({ id: 2, name: 'bad.pdf', status: 'failed', error: 'boom' })], folder({ done: 1, failed: 1 }))
    renderLibrary()
    await screen.findByText('bad.pdf')
    await userEvent.click(screen.getByRole('button', { name: /failed.*1|1.*failed/i }))
    await waitFor(() => expect(screen.queryByText('fundsmith_factsheet_2026-08.pdf')).not.toBeInTheDocument())
    expect(screen.getByText('bad.pdf')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /all/i }))
    expect(await screen.findByText('fundsmith_factsheet_2026-08.pdf')).toBeInTheDocument()
  })

  it('shows the error and retries a failed file without navigating', async () => {
    let retried = 0
    use([file({ id: 9, status: 'failed', error: 'Extraction failed after 2 tries' })], folder({ failed: 1 }))
    server.use(
      http.post('/api/files/9/retry', () => {
        retried++
        return HttpResponse.json({ id: 9, status: 'queued' })
      }),
    )
    renderLibrary()
    expect(await screen.findByText('Extraction failed after 2 tries')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /retry/i }))
    await waitFor(() => expect(retried).toBe(1))
    expect(screen.queryByTestId('where')).not.toBeInTheDocument()
  })
})

describe('L2 syncing', () => {
  it('posts Sync now, and disables it while files are queued or processing', async () => {
    let posted = 0
    use([file({ status: 'queued' })], folder({ queued: 1, done: 3 }))
    server.use(
      http.post('/api/folder/sync', () => {
        posted++
        return HttpResponse.json({ queued: 0, ignored: 0 })
      }),
    )
    renderLibrary()
    await screen.findByText('fundsmith_factsheet_2026-08.pdf')
    await waitFor(() => expect(screen.getByRole('button', { name: /sync now/i })).toBeDisabled())
    expect(posted).toBe(0)
  })

  it('posts when idle', async () => {
    let posted = 0
    use([file()])
    server.use(
      http.post('/api/folder/sync', () => {
        posted++
        return HttpResponse.json({ queued: 1, ignored: 0 })
      }),
    )
    renderLibrary()
    await screen.findByText('fundsmith_factsheet_2026-08.pdf')
    await userEvent.click(screen.getByRole('button', { name: /sync now/i }))
    await waitFor(() => expect(posted).toBe(1))
  })

  it('refetches the list every 5 s while anything is queued or processing', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    let calls = 0
    use([file({ status: 'processing' })], folder({ processing: 1 }))
    server.use(
      http.get('/api/files', () => {
        calls++
        return HttpResponse.json([file({ status: 'processing' })])
      }),
    )
    renderLibrary()
    await screen.findByText('fundsmith_factsheet_2026-08.pdf')
    const before = calls
    await act(() => vi.advanceTimersByTimeAsync(5100))
    await waitFor(() => expect(calls).toBeGreaterThan(before))
  })

  it('does not poll when nothing is pending', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    let calls = 0
    use([file()])
    server.use(
      http.get('/api/files', () => {
        calls++
        return HttpResponse.json([file()])
      }),
    )
    renderLibrary()
    await screen.findByText('fundsmith_factsheet_2026-08.pdf')
    const before = calls
    await act(() => vi.advanceTimersByTimeAsync(5100))
    expect(calls).toBe(before)
  })
})

describe('L3 reconnect', () => {
  it('shows the Reconnect alert linking to Google start and disables Sync now', async () => {
    use([file()], folder({ done: 1 }, { needs_reconnect: true }))
    renderLibrary()
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/access was removed/i)
    expect(within(alert).getByRole('link', { name: /reconnect google drive/i })).toHaveAttribute(
      'href',
      '/api/auth/google/start',
    )
    expect(screen.getByRole('button', { name: /sync now/i })).toBeDisabled()
    expect(screen.getByText('fundsmith_factsheet_2026-08.pdf')).toBeInTheDocument()
  })
})

describe('L4 empty', () => {
  it('explains an empty folder', async () => {
    use([], folder({}))
    renderLibrary()
    expect(await screen.findByText(/no documents the app can read yet/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /choose a different folder/i })).toHaveAttribute('href', '/connect')
  })
})
