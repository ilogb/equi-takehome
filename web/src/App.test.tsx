import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from './App'
import { QueryProvider } from './QueryProvider'
import { server } from './test/server'

function Where() {
  const l = useLocation()
  return <div data-testid="where">{l.pathname + l.search}</div>
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <QueryProvider retry={false}>
        <App />
        <Where />
      </QueryProvider>
    </MemoryRouter>,
  )
}

describe('route guard', () => {
  it('sends a 401 to /connect', async () => {
    server.use(http.get('/api/auth/me', () => HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })))
    renderAt('/library')
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/connect'))
    expect(screen.getByRole('link', { name: /sign in with google/i })).toBeInTheDocument()
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
})
