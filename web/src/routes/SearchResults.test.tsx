import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { QueryProvider } from '@/QueryProvider'
import { server } from '@/test/server'
import { SearchResults } from './SearchResults'

const hit = (over: object = {}) => ({
  document_id: 11,
  file_name: 'fundsmith_factsheet.pdf',
  path: 'Factsheets/fundsmith_factsheet.pdf',
  doc_type: 'Factsheet',
  manager: 'Fundsmith',
  funds: ['Fundsmith Equity Fund'],
  as_of_date: '2026-08-31',
  tags: ['global equity'],
  snippet: 'Quarterly performance of the Fundsmith fund',
  score: 0.9,
  ...over,
})

function Url() {
  const l = useLocation()
  return <div data-testid="url">{l.pathname + l.search}</div>
}
function Doc() {
  const nav = useNavigate()
  return <button onClick={() => nav(-1)}>back</button>
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Url />
      <QueryProvider retry={false}>
        <Routes>
          <Route path="/search" element={<SearchResults />} />
          <Route path="/documents/:id" element={<Doc />} />
        </Routes>
      </QueryProvider>
    </MemoryRouter>,
  )
}

describe('Find mode', () => {
  it('lists hits with snippet, tags, path, highlight and a Similar panel', async () => {
    server.use(
      http.get('/api/search', () =>
        HttpResponse.json({
          hits: [hit(), hit({ document_id: 12, file_name: 'other.pdf', path: 'X/other.pdf', tags: ['bonds'] })],
          similar_for_first: [hit({ document_id: 13, file_name: 'sibling.pdf', path: 'Y/sibling.pdf' })],
        }),
      ),
    )
    renderAt('/search?q=fundsmith&mode=find')
    expect(await screen.findByText('fundsmith_factsheet.pdf')).toBeInTheDocument()
    expect(screen.getByText('Factsheets/fundsmith_factsheet.pdf')).toBeInTheDocument()
    expect(screen.getByText('global equity')).toBeInTheDocument()
    const marks = document.querySelectorAll('mark')
    expect(marks.length).toBeGreaterThan(0)
    expect(marks[0].textContent?.toLowerCase()).toBe('fundsmith')
    const similar = screen.getByRole('complementary', { name: /similar documents/i })
    const link = within(similar).getByRole('link', { name: /sibling\.pdf/ })
    expect(link).toHaveAttribute('href', '/documents/13')
  })

  it('selecting another hit loads its similar documents', async () => {
    const queries: string[] = []
    server.use(
      http.get('/api/search', ({ request }) => {
        const q = new URL(request.url).searchParams.get('q')!
        queries.push(q)
        if (q === 'fundsmith')
          return HttpResponse.json({
            hits: [hit(), hit({ document_id: 12, file_name: 'other.pdf', manager: 'Alderbank', funds: ['Alder Fund'] })],
            similar_for_first: [],
          })
        return HttpResponse.json({
          hits: [hit({ document_id: 12, file_name: 'other.pdf' }), hit({ document_id: 14, file_name: 'alder_sibling.pdf' })],
          similar_for_first: [],
        })
      }),
    )
    renderAt('/search?q=fundsmith&mode=find')
    await userEvent.click(await screen.findByRole('button', { name: /select other\.pdf/i }))
    const similar = screen.getByRole('complementary', { name: /similar documents/i })
    expect(await within(similar).findByRole('link', { name: /alder_sibling\.pdf/ })).toBeInTheDocument()
    expect(within(similar).queryByRole('link', { name: /^other\.pdf/ })).not.toBeInTheDocument()
    expect(queries.length).toBe(2)
  })

  it('shows the empty state for no results', async () => {
    server.use(http.get('/api/search', () => HttpResponse.json({ hits: [], similar_for_first: [] })))
    renderAt('/search?q=zzz&mode=find')
    expect(await screen.findByText(/no documents match/i)).toBeInTheDocument()
  })

  it('renders snippet text as text, not HTML', async () => {
    server.use(
      http.get('/api/search', () =>
        HttpResponse.json({ hits: [hit({ snippet: '<img src=x onerror=alert(1)> fundsmith' })], similar_for_first: [] }),
      ),
    )
    renderAt('/search?q=fundsmith')
    await screen.findByText('fundsmith_factsheet.pdf')
    expect(document.querySelector('img')).toBeNull()
    expect(screen.getByText(/<img src=x/)).toBeInTheDocument()
  })
})

const answer = {
  text: 'Fundsmith returned 8.42% over the year.',
  table: { columns: ['Fund', 'Return'], rows: [['Fundsmith Equity', '8.42%'], ['Other', '−1.10%']] },
  sources: [{ document_id: 11, file_name: 'fundsmith_factsheet.pdf' }],
  steps: ['Looked up return rows', 'Filtered to 1y'],
}

describe('Analyze mode', () => {
  it('shows loading state then the answer, table, sources and steps', async () => {
    server.use(http.post('/api/analyze', () => HttpResponse.json(answer)))
    renderAt('/search?q=how%20did%20fundsmith%20do&mode=analyze')
    expect(screen.getByText(/looking up your data \(up to 5 lookups\)/i)).toBeInTheDocument()
    expect(await screen.findByText(answer.text)).toBeInTheDocument()
    expect(screen.queryByText(/looking up your data/i)).not.toBeInTheDocument()
    const cell = screen.getByRole('cell', { name: '8.42%' })
    expect(cell.className).toMatch(/text-right/)
    expect(screen.getByRole('cell', { name: 'Fundsmith Equity' }).className).not.toMatch(/text-right/)
    expect(screen.getByRole('link', { name: /fundsmith_factsheet\.pdf/ })).toHaveAttribute('href', '/documents/11')
    expect(screen.getByText('Looked up return rows')).toBeInTheDocument()
  })

  it("renders a can't-answer text as-is without a table", async () => {
    const text = "Couldn't answer right now — try again."
    server.use(http.post('/api/analyze', () => HttpResponse.json({ text, table: null, sources: [], steps: [] })))
    renderAt('/search?q=what&mode=analyze')
    expect(await screen.findByText(text)).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('Back from a source returns to the same URL without re-POSTing', async () => {
    const post = vi.fn(() => HttpResponse.json(answer))
    server.use(http.post('/api/analyze', post))
    const url = '/search?q=how%20did%20fundsmith%20do&mode=analyze'
    renderAt(url)
    await userEvent.click(await screen.findByRole('link', { name: /fundsmith_factsheet\.pdf/ }))
    await userEvent.click(screen.getByRole('button', { name: 'back' }))
    expect(await screen.findByText(answer.text)).toBeInTheDocument()
    expect(screen.getByTestId('url')).toHaveTextContent(url)
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1))
  })
})
