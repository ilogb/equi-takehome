import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import App from './App'
import { QueryProvider } from './QueryProvider'
import { server } from './test/server'

function Where() {
  const l = useLocation()
  return <div data-testid="where">{l.pathname + l.search}</div>
}

function Back() {
  const nav = useNavigate()
  return <button onClick={() => nav(-1)}>history back</button>
}

function renderAt(path: string | string[]) {
  const entries = Array.isArray(path) ? path : [path]
  return render(
    <MemoryRouter initialEntries={entries} initialIndex={entries.length - 1}>
      <QueryProvider retry={false}>
        <App />
        <Where />
        <Back />
      </QueryProvider>
    </MemoryRouter>,
  )
}

describe('route guard', () => {
  it('sends a 401 to /connect', async () => {
    server.use(http.get('/api/auth/me', () => HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })))
    renderAt('/library')
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/connect'))
    expect(await screen.findByRole('link', { name: /continue with google/i })).toBeInTheDocument()
  })

  it('shows the shell for a signed-in user', async () => {
    renderAt('/data')
    expect(await screen.findByRole('link', { name: 'Library' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Data' })).toBeInTheDocument()
    expect(await screen.findByRole('status')).toHaveTextContent('Synced')
  })
})

describe('global 401 handling', () => {
  it('redirects to /connect when a query returns 401 mid-session', async () => {
    server.use(http.get('/api/folder', () => HttpResponse.json({ detail: 'expired' }, { status: 401 })))
    renderAt('/data')
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/connect'))
  })
})

describe('header search', () => {
  it('navigates to /search with the chosen mode', async () => {
    const user = userEvent.setup()
    renderAt('/library')
    const box = await screen.findByRole('searchbox', { name: 'Search' })
    await user.type(box, 'net return 2024')
    await user.click(screen.getByRole('radio', { name: 'Analyze' }))
    await user.type(box, '{Enter}')
    await waitFor(() =>
      expect(screen.getByTestId('where')).toHaveTextContent('/search?q=net+return+2024&mode=analyze'),
    )
  })

  it('defaults to Find', async () => {
    const user = userEvent.setup()
    renderAt('/library')
    await user.type(await screen.findByRole('searchbox', { name: 'Search' }), 'nav{Enter}')
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/search?q=nav&mode=find'))
  })

  it('the search button submits', async () => {
    const user = userEvent.setup()
    renderAt('/library')
    await user.type(await screen.findByRole('searchbox', { name: 'Search' }), 'nav')
    await user.click(screen.getByRole('button', { name: 'Search' }))
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/search?q=nav&mode=find'))
  })

  it('an empty box cannot be submitted, by button or Enter', async () => {
    const user = userEvent.setup()
    renderAt('/library')
    const button = await screen.findByRole('button', { name: 'Search' })
    expect(button).toHaveAttribute('aria-disabled', 'true')
    await user.click(button)
    await user.type(screen.getByRole('searchbox', { name: 'Search' }), '   {Enter}')
    expect(screen.getByTestId('where')).toHaveTextContent('/library')
  })

  it('on /search, switching mode re-runs the unedited query in the new mode', async () => {
    const user = userEvent.setup()
    renderAt('/search?q=nav&mode=find')
    await user.click(await screen.findByRole('radio', { name: 'Analyze' }))
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/search?q=nav&mode=analyze'))
  })

  it('on /search, switching mode after editing the box waits for Enter', async () => {
    const user = userEvent.setup()
    renderAt('/search?q=nav&mode=find')
    const box = await screen.findByRole('searchbox', { name: 'Search' })
    await user.type(box, ' history')
    await user.click(screen.getByRole('radio', { name: 'Analyze' }))
    expect(screen.getByTestId('where')).toHaveTextContent('/search?q=nav&mode=find')
    await user.type(box, '{Enter}')
    await waitFor(() =>
      expect(screen.getByTestId('where')).toHaveTextContent('/search?q=nav+history&mode=analyze'),
    )
  })

  it('the box and mode follow the URL on Back', async () => {
    const user = userEvent.setup()
    renderAt(['/search?q=first&mode=analyze', '/search?q=second&mode=find'])
    const box = await screen.findByRole('searchbox', { name: 'Search' })
    expect(box).toHaveValue('second')
    expect(screen.getByRole('radio', { name: 'Find' })).toBeChecked()
    await user.click(screen.getByRole('button', { name: 'history back' }))
    await waitFor(() => expect(box).toHaveValue('first'))
    expect(screen.getByRole('radio', { name: 'Analyze' })).toBeChecked()
  })

  it('submitting the same query and mode again re-runs it', async () => {
    const get = vi.fn(() => HttpResponse.json({ hits: [], similar_for_first: [] }))
    server.use(http.get('/api/search', get))
    const user = userEvent.setup()
    renderAt('/search?q=nav&mode=find')
    await waitFor(() => expect(get).toHaveBeenCalledTimes(1))
    await user.click(await screen.findByRole('button', { name: 'Search' }))
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2))
  })

  it('shows the search as busy while Analyze runs and ignores repeat clicks', async () => {
    let posts = 0
    let release!: () => void
    const answered = new Promise<void>((r) => (release = r))
    server.use(
      http.post('/api/analyze', async () => {
        posts += 1
        await answered
        return HttpResponse.json({ text: 'Done.', table: null, sources: [], steps: [] })
      }),
    )
    const user = userEvent.setup()
    renderAt('/library')
    await user.type(await screen.findByRole('searchbox', { name: 'Search' }), 'best fund')
    await user.click(screen.getByRole('radio', { name: 'Analyze' }))
    const button = screen.getByRole('button', { name: 'Search' })
    await user.click(button)
    await waitFor(() => expect(button).toHaveAttribute('aria-busy', 'true'))
    await user.click(button)
    await user.type(screen.getByRole('searchbox', { name: 'Search' }), '{Enter}')
    expect(posts).toBe(1)
    release()
    await waitFor(() => expect(button).not.toHaveAttribute('aria-busy'))
    expect(posts).toBe(1)
  })
})
