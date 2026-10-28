import { render, screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { QueryProvider } from '@/QueryProvider'
import { server } from '@/test/server'
import { LibraryDashboard } from './LibraryDashboard'

const dashboard = {
  documents: { total: 14, done: 11, needs_review: 2, failed: 1, processing: 0 },
  figures: { total: 58763, needs_review: 30, conflicts: 30 },
  entities: { funds: 29, accounts: 1 },
  one_year: [
    { entity: 'Man AHL Diversified plc', fund_id: 3, period_end: '2026-08-31', return: '0.3678', benchmark: null },
    { entity: 'JPMorgan Equity Focus ETF', fund_id: 2, period_end: '2026-09-30', return: '0.1032', benchmark: '0.1574' },
    { entity: 'Fundsmith SICAV Equity Fund', fund_id: 4, period_end: '2026-08-31', return: '-0.019', benchmark: '0.181' },
  ],
  aum: [
    { entity: 'Fundsmith SICAV Equity Fund', fund_id: 4, period_end: '2026-08-31', value: '4500000000', currency: 'EUR' },
    { entity: 'Man AHL Diversified plc', fund_id: 3, period_end: '2026-08-28', value: '313174253', currency: 'USD' },
  ],
}

function renderDashboard(body: object = dashboard) {
  server.use(http.get('/api/dashboard', () => HttpResponse.json(body)))
  return render(
    <MemoryRouter>
      <QueryProvider retry={false}>
        <LibraryDashboard />
      </QueryProvider>
    </MemoryRouter>,
  )
}

describe('LibraryDashboard', () => {
  it('shows the four headline numbers, with review and conflict counts linking to filtered Data', async () => {
    renderDashboard()
    const docs = await screen.findByRole('group', { name: 'Documents' })
    expect(docs).toHaveTextContent('14')
    expect(within(docs).getByRole('link', { name: /2 need review/i })).toHaveAttribute('href', '/library?status=needs_review')
    expect(screen.getByRole('group', { name: 'Funds tracked' })).toHaveTextContent('29')
    expect(screen.getByRole('group', { name: 'Funds tracked' })).toHaveTextContent('1 account')
    const figures = screen.getByRole('group', { name: 'Data points' })
    expect(figures).toHaveTextContent('58,763')
    expect(within(figures).getByRole('link', { name: /30 need review/i })).toHaveAttribute('href', '/data?needs_review=true')
    const differ = screen.getByRole('group', { name: 'Sources differ' })
    expect(differ).toHaveTextContent('30')
    expect(within(differ).getByRole('link')).toHaveAttribute('href', '/data?conflict=true')
  })

  it('charts each fund’s 1-year return against its benchmark, best first, linking to its rows', async () => {
    renderDashboard()
    const chart = await screen.findByRole('figure', { name: /1-year return vs benchmark/i })
    expect(within(chart).getByText('Fund')).toBeInTheDocument() // legend
    expect(within(chart).getByText('Benchmark')).toBeInTheDocument()
    const links = within(chart).getAllByRole('link')
    expect(links.map((l) => l.textContent)).toEqual([
      expect.stringContaining('Man AHL Diversified plc'),
      expect.stringContaining('JPMorgan Equity Focus ETF'),
      expect.stringContaining('Fundsmith SICAV Equity Fund'),
    ])
    expect(links[1]).toHaveAttribute('href', '/data?fund=2&measure=return&period_kind=1y')
    expect(links[1]).toHaveTextContent('10.32%')
    expect(links[1]).toHaveTextContent('15.74%')
    expect(links[0]).toHaveTextContent('no benchmark')
    expect(links[2]).toHaveTextContent('−1.90%')
  })

  it('lists AUM largest first, each in its own currency', async () => {
    renderDashboard()
    const aum = await screen.findByRole('figure', { name: /assets under management/i })
    const links = within(aum).getAllByRole('link')
    expect(links[0]).toHaveTextContent('Fundsmith SICAV Equity Fund')
    expect(links[0]).toHaveTextContent('€4.5B')
    expect(links[0]).toHaveAttribute('href', '/data?fund=4&measure=aum')
    expect(links[1]).toHaveTextContent('$313.17M')
  })

  it('hides the charts when there are no figures yet', async () => {
    renderDashboard({ ...dashboard, one_year: [], aum: [], figures: { total: 0, needs_review: 0, conflicts: 0 } })
    expect(await screen.findByRole('group', { name: 'Documents' })).toBeInTheDocument()
    expect(screen.queryByRole('figure')).not.toBeInTheDocument()
  })

  it('renders nothing if the summary fails to load', async () => {
    server.use(http.get('/api/dashboard', () => HttpResponse.json({ detail: 'boom' }, { status: 500 })))
    const { container } = render(
      <MemoryRouter>
        <QueryProvider retry={false}>
          <LibraryDashboard />
        </QueryProvider>
      </MemoryRouter>,
    )
    await new Promise((r) => setTimeout(r, 50))
    expect(container).toBeEmptyDOMElement()
  })
})
