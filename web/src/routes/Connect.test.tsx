import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { QueryProvider } from '@/QueryProvider'
import { server } from '@/test/server'
import { Connect } from './Connect'

function Where() {
  const l = useLocation()
  return <div data-testid="where">{l.pathname + l.search}</div>
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <QueryProvider retry={false}>
        <Connect />
        <Where />
      </QueryProvider>
    </MemoryRouter>,
  )
}

const signedOut = () =>
  server.use(http.get('/api/auth/me', () => HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })))

const signedInNoFolder = () =>
  server.use(
    http.get('/api/auth/me', () =>
      HttpResponse.json({ email: 'a@example.com', name: 'A', needs_reconnect: false, has_folder: false }),
    ),
    http.get('/api/folders', ({ request }) => {
      const q = new URL(request.url).searchParams.get('q') ?? ''
      const all = [
        { id: 'f1', name: 'Fund documents' },
        { id: 'f2', name: 'Fundraising' },
        { id: 'g1', name: 'Taxes' },
      ]
      return HttpResponse.json(all.filter((f) => f.name.toLowerCase().includes(q.toLowerCase())))
    }),
  )

const status = (counts: Record<string, number>, over: object = {}) => ({
  name: 'Fund documents',
  last_synced_at: '2026-10-28T10:40:00Z',
  last_error: null,
  counts_by_status: counts,
  needs_reconnect: false,
  ...over,
})

describe('C1 signed out', () => {
  it('offers Continue with Google as a plain link to the start route', async () => {
    signedOut()
    renderAt('/connect')
    const link = await screen.findByRole('link', { name: /continue with google/i })
    expect(link).toHaveAttribute('href', '/api/auth/google/start')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})

describe('C2 not on the list', () => {
  it('shows the access-list alert for ?error=not_allowed and keeps the param', async () => {
    signedOut()
    renderAt('/connect?error=not_allowed')
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/isn.t on the access list/i)
    expect(screen.getByRole('link', { name: /use another google account/i })).toHaveAttribute(
      'href',
      '/api/auth/google/start',
    )
    expect(screen.getByTestId('where')).toHaveTextContent('/connect?error=not_allowed')
  })
})

describe('C3 choosing a folder', () => {
  it('searches Drive folders and PUTs the chosen one', async () => {
    signedInNoFolder()
    let body: unknown
    server.use(
      http.put('/api/folder', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json(status({ queued: 2 }, { last_synced_at: null }))
      }),
      http.get('/api/folder', () => HttpResponse.json(status({ queued: 2 }, { last_synced_at: null }))),
    )
    const user = userEvent.setup()
    renderAt('/connect')
    const search = await screen.findByRole('searchbox', { name: /search your folders/i })
    expect(await screen.findByRole('radio', { name: /taxes/i })).toBeInTheDocument()
    await user.type(search, 'fund')
    await waitFor(() => expect(screen.queryByRole('radio', { name: /taxes/i })).not.toBeInTheDocument())
    await user.click(screen.getByRole('radio', { name: /fund documents/i }))
    await user.click(screen.getByRole('button', { name: /use this folder/i }))
    await waitFor(() => expect(body).toEqual({ folder_id: 'f1' }))
    expect(await screen.findByRole('progressbar')).toBeInTheDocument()
  })

  it('shows the server message when the folder is rejected', async () => {
    signedInNoFolder()
    server.use(
      http.put('/api/folder', () =>
        HttpResponse.json({ detail: 'folder not found, or not shared with this Google account' }, { status: 400 }),
      ),
    )
    const user = userEvent.setup()
    renderAt('/connect')
    await user.click(await screen.findByRole('radio', { name: /taxes/i }))
    await user.click(screen.getByRole('button', { name: /use this folder/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/folder not found/i)
  })

  it('asks for confirmation in the page before replacing an existing folder', async () => {
    signedInNoFolder()
    server.use(
      http.get('/api/auth/me', () =>
        HttpResponse.json({ email: 'a@example.com', name: 'A', needs_reconnect: false, has_folder: true }),
      ),
      http.get('/api/folder', () => HttpResponse.json(status({ done: 3 }))),
    )
    let puts = 0
    server.use(
      http.put('/api/folder', () => {
        puts += 1
        return HttpResponse.json(status({ queued: 1 }, { last_synced_at: null }))
      }),
    )
    const user = userEvent.setup()
    renderAt('/connect')
    await user.click(await screen.findByRole('button', { name: /change folder/i }))
    await user.click(await screen.findByRole('radio', { name: /taxes/i }))
    await user.click(screen.getByRole('button', { name: /use this folder/i }))
    const confirm = await screen.findByRole('alertdialog')
    expect(confirm).toHaveTextContent(/removes everything/i)
    expect(puts).toBe(0)
    await user.click(within(confirm).getByRole('button', { name: /cancel/i }))
    expect(puts).toBe(0)
    await user.click(screen.getByRole('button', { name: /use this folder/i }))
    await user.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: /replace folder/i }))
    await waitFor(() => expect(puts).toBe(1))
  })
})

describe('returning to /connect after a first choice', () => {
  it('still asks for confirmation before replacing the folder', async () => {
    signedInNoFolder()
    let chosen = false
    let puts = 0
    server.use(
      http.get('/api/auth/me', () =>
        HttpResponse.json({ email: 'a@example.com', name: 'A', needs_reconnect: false, has_folder: chosen }),
      ),
      http.get('/api/folder', () => HttpResponse.json(status({ done: 1 }))),
      http.put('/api/folder', () => {
        puts += 1
        chosen = true
        return HttpResponse.json(status({ done: 1 }))
      }),
    )
    function Remountable() {
      const [on, setOn] = useState(true)
      return (
        <>
          <button onClick={() => setOn((v) => !v)}>toggle</button>
          {on && <Connect />}
        </>
      )
    }
    const user = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/connect']}>
        <QueryProvider retry={false}>
          <Remountable />
        </QueryProvider>
      </MemoryRouter>,
    )
    await user.click(await screen.findByRole('radio', { name: /taxes/i }))
    await user.click(screen.getByRole('button', { name: /use this folder/i }))
    await waitFor(() => expect(puts).toBe(1))
    await screen.findByRole('progressbar')
    await user.click(screen.getByRole('button', { name: 'toggle' }))
    await user.click(screen.getByRole('button', { name: 'toggle' }))
    await user.click(await screen.findByRole('button', { name: /change folder/i }))
    await user.click(await screen.findByRole('radio', { name: /fund documents/i }))
    await user.click(screen.getByRole('button', { name: /use this folder/i }))
    expect(await screen.findByRole('alertdialog')).toBeInTheDocument()
    expect(puts).toBe(1)
    await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: /replace folder/i }))
    await waitFor(() => expect(puts).toBe(2))
  })
})

describe('C4 first sync', () => {
  it('shows n of m processed (unsupported not counted) and polls until finished', async () => {
    signedInNoFolder()
    let calls = 0
    server.use(
      http.get('/api/auth/me', () =>
        HttpResponse.json({ email: 'a@example.com', name: 'A', needs_reconnect: false, has_folder: true }),
      ),
      http.get('/api/folder', () => {
        calls += 1
        return HttpResponse.json(
          calls === 1
            ? status({ done: 4, needs_review: 1, processing: 3, queued: 5, unsupported: 1 })
            : status({ done: 12, needs_review: 2, unsupported: 1 }),
        )
      }),
    )
    renderAt('/connect')
    expect(await screen.findByText('5 of 13 processed')).toBeInTheDocument()
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '5')
    expect(await screen.findByText('14 of 14 processed', {}, { timeout: 5000 })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /open library/i })).toHaveAttribute('href', '/library')
    vi.useFakeTimers()
    try {
      await vi.advanceTimersByTimeAsync(10_000)
    } finally {
      vi.useRealTimers()
    }
    expect(calls).toBe(2)
  }, 15000)
})
