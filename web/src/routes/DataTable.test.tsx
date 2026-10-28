import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeAll, describe, expect, it } from 'vitest'
import { QueryProvider } from '@/QueryProvider'
import { server } from '@/test/server'
import { DataTable } from './DataTable'

beforeAll(() => {
  // cmdk needs these in jsdom
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  Element.prototype.scrollIntoView ??= () => {}
})

const row = (over: object = {}) => ({
  id: 1,
  document_id: 11,
  document_name: 'alderbank_performance.pdf',
  manager: 'Alderbank',
  fund_id: 5,
  entity: 'Alderbank European Equity Fund',
  entity_kind: 'fund',
  share_class: 'I EUR Acc',
  measure: 'return',
  period_kind: 'month',
  period_end: '2026-01-31',
  value: '0.0321000000',
  value_as_written: '3.21%',
  unit: 'percent',
  currency: 'EUR',
  benchmark_name: null,
  table_index: 0,
  row_index: 0,
  col_index: 0,
  needs_review: false,
  review_reason: null,
  conflict: false,
  ...over,
})

const T1 = [
  row({ id: 1, entity: 'Man AHL Diversified', share_class: 'Class DN USD', value: '0.0842', document_id: 10, document_name: 'man-ahl_factsheet.pdf', currency: 'USD' }),
  row({ id: 2 }),
  row({ id: 3, share_class: 'A EUR Acc', value: '0.0312' }),
  row({ id: 4, entity: 'Northwind Global Macro Fund, L.P.', share_class: 'Founders', value: '0.0237', conflict: true, document_id: 20, document_name: 'northwind_monthly.csv' }),
  row({ id: 5, entity: 'Northwind Global Macro Fund, L.P.', share_class: 'Founders', value: '0.0235', conflict: true, document_id: 21, document_name: 'northwind_q1.pdf' }),
  row({ id: 6, entity: 'Kestrel Ridge Long/Short Equity Fund', share_class: null, value: '0.0190', needs_review: true, review_reason: 'Net and gross both stated', document_id: 30, document_name: 'kestrel.pdf' }),
  row({ id: 7, entity: 'UVic MPP', entity_kind: 'account', measure: 'account_value', period_kind: 'other', value: '24963108.45', currency: 'USD', share_class: null, document_id: 40, document_name: 'uvic_statement.pdf' }),
]

/** Records every /api/rows request URL. */
function useRows(rows: object[] = T1, total = rows.length) {
  const seen: URL[] = []
  server.use(
    http.get('/api/rows', ({ request }) => {
      seen.push(new URL(request.url))
      return HttpResponse.json({ rows, total })
    }),
    http.get('/api/funds', () =>
      HttpResponse.json([{ id: 5, name: 'Alderbank European Equity Fund', manager: 'Alderbank', share_classes: ['A EUR Acc', 'I EUR Acc'], documents: 1 }]),
    ),
    http.get('/api/meta', () =>
      HttpResponse.json({
        measures: ['return', 'account_value'],
        period_kinds: ['month', 'ytd'],
        min_period_end: '2025-01-31',
        max_period_end: '2026-09-30',
        managers: ['Alderbank', 'Fundsmith'],
      }),
    ),
  )
  return seen
}

function Url() {
  const l = useLocation()
  return <div data-testid="url">{l.pathname + l.search}</div>
}

function renderData(path = '/data') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Url />
      <QueryProvider retry={false}>
        <Routes>
          <Route path="/data" element={<DataTable />} />
          <Route path="/documents/:id" element={<p>doc page</p>} />
        </Routes>
      </QueryProvider>
    </MemoryRouter>,
  )
}

const url = () => screen.getByTestId('url').textContent!
const lastQ = (seen: URL[]) => seen[seen.length - 1]!.searchParams

describe('T1 default', () => {
  it('has the seven columns and one row per number', async () => {
    useRows()
    renderData('/data?measure=return&period_kind=month')
    await screen.findByText('Man AHL Diversified')
    const heads = screen.getAllByRole('columnheader').map((h) => h.textContent?.trim())
    expect(heads).toEqual(['Fund or account', 'Share class', 'Period', 'Measure', 'Value', 'Markers', 'Source'])
    const man = screen.getByText('Man AHL Diversified').closest('tr')!
    expect(within(man).getByText('Class DN USD')).toBeInTheDocument()
    expect(within(man).getByText('month · 2026-01-31')).toBeInTheDocument()
    expect(within(man).getByText('8.42%')).toBeInTheDocument()
    const src = within(man).getByRole('link', { name: 'man-ahl_factsheet.pdf' })
    expect(src).toHaveAttribute('href', '/documents/10-man-ahl-factsheet')
    const uvic = screen.getByText('UVic MPP').closest('tr')!
    expect(within(uvic).getByText('$24,963,108.45')).toBeInTheDocument()
    expect(within(uvic).getByText('Account value')).toBeInTheDocument()
  })

  it('keeps A EUR and I EUR as separate rows without conflict markers', async () => {
    useRows()
    renderData()
    const i = (await screen.findByText('I EUR Acc')).closest('tr')!
    const a = screen.getByText('A EUR Acc').closest('tr')!
    expect(i).not.toBe(a)
    expect(within(i).queryByRole('img')).toBeNull()
    expect(within(a).queryByRole('img')).toBeNull()
  })

  it('shows the sources-differ tooltip naming both documents, and the review reason', async () => {
    useRows()
    renderData()
    const founders = await screen.findAllByRole('img', { name: /sources differ/i })
    expect(founders).toHaveLength(2)
    expect(founders[0]).toHaveAttribute('title', expect.stringContaining('2.37% in northwind_monthly.csv'))
    expect(founders[0]).toHaveAttribute('title', expect.stringContaining('2.35% in northwind_q1.pdf'))
    expect(screen.getByRole('img', { name: 'Needs review: Net and gross both stated' })).toBeInTheDocument()
  })
})

describe('filters live in the URL and are sent to /api/rows', () => {
  it('reads the initial filters from the URL and ignores invalid ones', async () => {
    const seen = useRows()
    renderData('/data?measure=return&period_kind=bogus&start=2026-01-01&end=nope&conflict=true&limit=9999')
    await screen.findByText('Man AHL Diversified')
    const q = lastQ(seen)
    expect(q.get('measure')).toBe('return')
    expect(q.get('period_kind')).toBeNull()
    expect(q.get('start')).toBe('2026-01-01')
    expect(q.get('end')).toBeNull()
    expect(q.get('conflict')).toBe('true')
    expect(Number(q.get('limit'))).toBeLessThanOrEqual(500)
  })

  it('T3: the measure filter groups fund measures and account measures', async () => {
    const seen = useRows()
    renderData()
    await screen.findByText('Man AHL Diversified')
    await userEvent.click(screen.getByRole('button', { name: /^measure/i }))
    const fund = await screen.findByRole('group', { name: 'Fund measures' })
    expect(within(fund).getAllByRole('option').map((o) => o.textContent)).toEqual(['Return', 'Benchmark return', 'AUM', 'NAV'])
    const acct = screen.getByRole('group', { name: 'Account measures · from statements' })
    expect(within(acct).getAllByRole('option').map((o) => o.textContent)).toEqual(['Account value', 'Account return'])
    await userEvent.click(within(acct).getByRole('option', { name: 'Account value' }))
    await waitFor(() => expect(url()).toContain('measure=account_value'))
    await waitFor(() => expect(lastQ(seen).get('measure')).toBe('account_value'))
  })

  it('fund filter sends the fund id; manager and period kind use meta', async () => {
    const seen = useRows()
    renderData()
    await screen.findByText('Man AHL Diversified')
    await userEvent.click(screen.getByRole('button', { name: /^fund or account/i }))
    await userEvent.click(await screen.findByRole('option', { name: 'Alderbank European Equity Fund' }))
    await waitFor(() => expect(lastQ(seen).get('fund')).toBe('5'))
    await userEvent.click(screen.getByRole('button', { name: /^manager/i }))
    await userEvent.click(await screen.findByRole('option', { name: 'Fundsmith' }))
    await waitFor(() => expect(lastQ(seen).get('manager')).toBe('Fundsmith'))
    await userEvent.click(screen.getByRole('button', { name: /^period kind/i }))
    await userEvent.click(await screen.findByRole('option', { name: 'ytd' }))
    await waitFor(() => expect(lastQ(seen).get('period_kind')).toBe('ytd'))
    expect(url()).toContain('fund=5')
    expect(url()).toContain('manager=Fundsmith')
  })

  it('date range and toggles', async () => {
    const seen = useRows()
    renderData()
    await screen.findByText('Man AHL Diversified')
    await userEvent.type(screen.getByLabelText('From'), '2026-01-01')
    await userEvent.type(screen.getByLabelText('To'), '2026-01-31')
    await userEvent.click(screen.getByRole('switch', { name: /needs review/i }))
    await userEvent.click(screen.getByRole('switch', { name: /sources differ/i }))
    await waitFor(() => {
      const q = lastQ(seen)
      expect(q.get('start')).toBe('2026-01-01')
      expect(q.get('end')).toBe('2026-01-31')
      expect(q.get('needs_review')).toBe('true')
      expect(q.get('conflict')).toBe('true')
    })
    expect(url()).toContain('needs_review=true')
  })
})

describe('server-side sort and pagination', () => {
  it('clicking Value sorts desc then asc through the API', async () => {
    const seen = useRows()
    renderData()
    await screen.findByText('Man AHL Diversified')
    expect(lastQ(seen).get('sort')).toBe('period_end')
    await userEvent.click(screen.getByRole('button', { name: /sort by value/i }))
    await waitFor(() => expect(lastQ(seen).get('sort')).toBe('value'))
    expect(lastQ(seen).get('order')).toBe('desc')
    expect(screen.getByRole('columnheader', { name: /value/i })).toHaveAttribute('aria-sort', 'descending')
    await userEvent.click(screen.getByRole('button', { name: /sort by value/i }))
    await waitFor(() => expect(lastQ(seen).get('order')).toBe('asc'))
    expect(url()).toContain('sort=value')
    expect(url()).toContain('order=asc')
  })

  it('pages with offset and shows the range', async () => {
    const seen = useRows(T1, 250)
    renderData()
    await screen.findByText('Man AHL Diversified')
    expect(screen.getByText(/1–7 of 250/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: 'Next' }))
    await waitFor(() => expect(lastQ(seen).get('offset')).toBe('100'))
    expect(url()).toContain('offset=100')
  })

  it('changing a filter resets to the first page', async () => {
    const seen = useRows(T1, 250)
    renderData('/data?offset=200')
    await screen.findByText('Man AHL Diversified')
    await userEvent.click(screen.getByRole('switch', { name: /needs review/i }))
    await waitFor(() => expect(lastQ(seen).get('needs_review')).toBe('true'))
    expect(Number(lastQ(seen).get('offset') ?? 0)).toBe(0)
    expect(url()).not.toContain('offset')
  })
})

describe('Export CSV', () => {
  it('links to /api/rows.csv with the current filters and no paging', async () => {
    useRows()
    renderData('/data?measure=return&start=2026-01-01&sort=value&order=asc&offset=100')
    await screen.findByText('Man AHL Diversified')
    const a = screen.getByRole('link', { name: /export csv/i })
    const u = new URL(a.getAttribute('href')!, 'http://x')
    expect(u.pathname).toBe('/api/rows.csv')
    expect(u.searchParams.get('measure')).toBe('return')
    expect(u.searchParams.get('start')).toBe('2026-01-01')
    expect(u.searchParams.get('sort')).toBe('value')
    expect(u.searchParams.get('offset')).toBeNull()
    expect(u.searchParams.get('limit')).toBeNull()
  })
})

describe('clearing filters', () => {
  it('each active filter has its own clear button that removes only that filter', async () => {
    useRows()
    renderData('/data?measure=return&conflict=true')
    await screen.findByText('Man AHL Diversified')
    await userEvent.click(screen.getByRole('button', { name: 'Clear measure' }))
    await waitFor(() => expect(url()).toBe('/data?conflict=true'))
    expect(screen.queryByRole('button', { name: 'Clear measure' })).not.toBeInTheDocument()
  })

  it('Clear all shows while any filter is active and resets them all', async () => {
    useRows()
    renderData('/data?measure=return&conflict=true&start=2026-01-01')
    await screen.findByText('Man AHL Diversified')
    await userEvent.click(screen.getByRole('button', { name: 'Clear all' }))
    await waitFor(() => expect(url()).toBe('/data'))
    expect(screen.queryByRole('button', { name: 'Clear all' })).not.toBeInTheDocument()
  })
})

describe('T2 empty after filtering', () => {
  it('shows an empty state and Clear filters resets the URL', async () => {
    useRows([], 0)
    renderData('/data?measure=aum&conflict=true')
    expect(await screen.findByText(/no rows match these filters/i)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Clear filters' }))
    await waitFor(() => expect(url()).toBe('/data'))
  })

  it('shows a plain empty message with no filters', async () => {
    useRows([], 0)
    renderData()
    expect(await screen.findByText(/no extracted rows yet/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Clear filters' })).toBeNull()
  })

  it('shows an error when the query fails', async () => {
    server.use(http.get('/api/rows', () => HttpResponse.json({ detail: 'x' }, { status: 500 })))
    server.use(http.get('/api/funds', () => HttpResponse.json([])), http.get('/api/meta', () => HttpResponse.json({ measures: [], period_kinds: [], min_period_end: null, max_period_end: null, managers: [] })))
    renderData()
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not load/i)
  })
})

describe('document filter', () => {
  it('passes a valid document_id to the API and the CSV link, and can be cleared', async () => {
    const user = userEvent.setup()
    const seen = useRows()
    renderData('/data?document_id=11')
    await screen.findByText('Man AHL Diversified')
    expect(lastQ(seen).get('document_id')).toBe('11')
    const csv = new URL(screen.getByRole('link', { name: /export csv/i }).getAttribute('href')!, 'http://x')
    expect(csv.searchParams.get('document_id')).toBe('11')
    const chip = screen.getByRole('switch', { name: /document/i })
    expect(chip).toHaveTextContent('man-ahl_factsheet.pdf')
    await user.click(chip)
    await waitFor(() => expect(url()).toBe('/data'))
    await waitFor(() => expect(lastQ(seen).get('document_id')).toBeNull())
  })

  it.each(['abc', '0', '-3', '1.5', ''])('drops an invalid document_id %j', async (bad) => {
    const seen = useRows()
    renderData(`/data?document_id=${bad}`)
    await screen.findByText('Man AHL Diversified')
    expect(lastQ(seen).get('document_id')).toBeNull()
    expect(screen.queryByRole('switch', { name: /document/i })).toBeNull()
  })
})
