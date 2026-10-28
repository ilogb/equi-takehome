import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { Link, MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { act } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { QueryProvider } from '@/QueryProvider'
import { server } from '@/test/server'
import { DocumentView } from './DocumentView'

const row = (over: object = {}) => ({
  id: 1,
  document_id: 5,
  document_name: 'man-ahl.pdf',
  manager: 'Man AHL',
  fund_id: 1,
  entity: 'Man AHL Diversified',
  entity_kind: 'fund',
  share_class: 'DN USD',
  measure: 'return',
  period_kind: 'month',
  period_end: '2026-01-31',
  value: '0.0842',
  value_as_written: '8.42%',
  unit: 'fraction',
  currency: 'USD',
  benchmark_name: null,
  table_index: 0,
  row_index: 0,
  col_index: 0,
  needs_review: false,
  review_reason: null,
  conflict: false,
  ...over,
})

const doc = (over: Record<string, unknown> = {}) => withTotal({
  id: 5,
  source_file_id: 9,
  name: 'man-ahl_factsheet_2026-08.pdf',
  path: 'Factsheets/man-ahl_factsheet_2026-08.pdf',
  mime_type: 'application/pdf',
  status: 'done',
  doc_type: 'Factsheet',
  manager: 'Man AHL',
  as_of_date: '2026-08-31',
  currency: 'USD',
  summary: null,
  tags: ['managed futures'],
  funds: [{ name: 'Man AHL Diversified', share_class: null }],
  file: fileRow(),
  tables: [
    { index: 0, title: 'Historical Performance', header: [['Year', 'Jan']], rows: [['2026', '8.42%']], rows_total: 1 },
    { index: 1, title: 'Cumulative Performance', header: [['Period', 'Return']], rows: [['1y', '9.10%']], rows_total: 1 },
  ],
  rows: [
    row(),
    row({ id: 2, period_end: '2026-02-28', value: '-0.0375', value_as_written: '(3.75%)', needs_review: true, review_reason: 'footnote 2 says restated' }),
    row({ id: 3, period_end: '2026-03-31', value: '0.0512', value_as_written: '5.12%', conflict: true }),
    row({ id: 4, measure: 'aum', period_kind: 'other', period_end: '2026-08-31', value: '24963108.45', value_as_written: '24,963,108.45', unit: 'currency' }),
  ],
  ...over,
})

/** The backend always sends rows_total; default it to the rows in the fixture. */
function withTotal<T extends { rows: unknown[]; rows_total?: number }>(d: T) {
  return { ...d, rows_total: d.rows_total ?? d.rows.length }
}

function fileRow(over: object = {}) {
  return {
    id: 9,
    name: 'man-ahl_factsheet_2026-08.pdf',
    path: 'Factsheets/man-ahl_factsheet_2026-08.pdf',
    mime_type: 'application/pdf',
    kind: 'pdf',
    status: 'done',
    error: null,
    missing_in_drive: false,
    drive_file_id: 'drv9',
    ...over,
  }
}

function use(d: object, f: object = {}, content?: () => Response) {
  server.use(
    http.get('/api/documents/5', () => HttpResponse.json({ ...d, file: { ...(d as { file: object }).file, ...f } })),
    http.get('/api/files/9/content', content ?? (() => new HttpResponse(new Uint8Array([1, 2, 3]), { headers: { 'Content-Type': 'application/pdf' } }))),
  )
}

function DataPage() {
  const l = useLocation()
  return <div data-testid="data-url">{l.pathname + l.search}</div>
}

function renderView(start = '/documents/5') {
  return render(
    <MemoryRouter initialEntries={[start]}>
      <QueryProvider retry={false}>
        <Routes>
          <Route path="/documents/:id" element={<DocumentView />} />
          <Route path="/library" element={<div>library page</div>} />
          <Route path="/data" element={<DataPage />} />
        </Routes>
        <Here />
      </QueryProvider>
    </MemoryRouter>,
  )
}

function Here() {
  const l = useLocation()
  return <div data-testid="here">{l.pathname + l.search}</div>
}

describe('D1 done PDF', () => {
  it('shows header metadata, the PDF streamed from the content URL, and a back link', async () => {
    use(doc())
    renderView()
    expect(await screen.findByRole('heading', { name: 'man-ahl_factsheet_2026-08.pdf' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /library/i })).toHaveAttribute('href', '/library')
    expect(screen.getByText('Man AHL Diversified')).toBeInTheDocument()
    expect(screen.getByText('2026-08-31')).toBeInTheDocument()
    expect(screen.getByText('managed futures')).toBeInTheDocument()
    expect(screen.getByText('Done')).toBeInTheDocument()
    const open = await screen.findByRole('link', { name: 'Open PDF' })
    expect(open).toHaveAttribute('href', '/api/files/9/content')
    expect(open).toHaveAttribute('target', '_blank')
    // Data points live in Data, not here: the page shows the source tables only.
    expect(screen.getByRole('heading', { name: /^source tables/i })).toBeInTheDocument()
    expect(screen.queryByRole('tab')).not.toBeInTheDocument()
    // A PDF has no in-page preview pane: the extraction gets the full width.
    expect(screen.queryByText(/opens in your browser/i)).not.toBeInTheDocument()
  })

  it('As printed has a per-table picker', async () => {
    const user = userEvent.setup()
    use(doc())
    renderView()
    await screen.findByRole('heading', { name: /man-ahl/ })
    const picker = await screen.findByRole('group', { name: /printed tables/i })
    expect(screen.getByRole('columnheader', { name: 'Jan' })).toBeInTheDocument()
    await user.click(within(picker).getByRole('button', { name: /cumulative performance/i }))
    expect(screen.getByRole('columnheader', { name: 'Return' })).toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: 'Jan' })).not.toBeInTheDocument()
  })

  it('Re-extract posts and reports', async () => {
    const user = userEvent.setup()
    use(doc())
    let posted = false
    server.use(http.post('/api/files/9/reextract', () => { posted = true; return HttpResponse.json({ id: 9, status: 'queued' }) }))
    renderView()
    await user.click(await screen.findByRole('button', { name: /re-extract/i }))
    await waitFor(() => expect(posted).toBe(true))
  })
})

describe('D2 needs review', () => {
  it('shows the status and keeps Re-extract available', async () => {
    use(doc({ status: 'needs_review' }))
    renderView()
    expect(await screen.findByText('Needs review')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /re-extract/i })).toBeEnabled()
  })
})

describe('D3 failed', () => {
  it('shows the error and Retry, which posts', async () => {
    const user = userEvent.setup()
    use(doc({ status: 'failed', tables: [], rows: [] }), fileRow({ status: 'failed', error: 'model returned incomplete output' }))
    let posted = false
    server.use(http.post('/api/files/9/retry', () => { posted = true; return HttpResponse.json({ id: 9, status: 'queued' }) }))
    renderView()
    expect(await screen.findByText('model returned incomplete output')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /re-extract/i })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    await waitFor(() => expect(posted).toBe(true))
    expect(await screen.findByRole('link', { name: 'Open PDF' })).toBeInTheDocument()
  })
})

describe('D4 statement', () => {
  it('explains the holdings table', async () => {
    use(
      doc({
        doc_type: 'Statement',
        tables: [{ index: 0, title: 'Holdings', header: [['Holding', 'Gain']], rows: [['Man AHL', '4.1%']], rows_total: 1 }],
        rows: [row({ measure: 'account_value', period_kind: 'other', value: '1000.5', value_as_written: '1,000.50' })],
      }),
    )
    renderView()
    expect(await screen.findByText(/per-holding gains are not fund returns/i)).toBeInTheDocument()
  })
})

describe('D5 scanned', () => {
  it('explains and offers no Retry or Re-extract', async () => {
    use(doc({ status: 'scanned_no_text', tables: [], rows: [] }), fileRow({ status: 'scanned_no_text' }))
    renderView()
    expect(await screen.findByText(/no text layer/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /retry|re-extract/i })).not.toBeInTheDocument()
  })
})

describe('D6 no longer in Drive', () => {
  it('shows the last-known path, keeps tables, disables Re-extract', async () => {
    use(doc(), fileRow(), () => HttpResponse.json({ detail: 'No longer in Drive' }, { status: 404 }))
    renderView()
    expect(await screen.findByText('No longer in Drive')).toBeInTheDocument()
    expect(screen.getByText(/last known at/i)).toBeInTheDocument()
    expect(screen.getAllByText('Factsheets/man-ahl_factsheet_2026-08.pdf').length).toBeGreaterThan(0)
    await waitFor(() => expect(screen.getByRole('button', { name: /re-extract/i })).toBeDisabled())
    expect(screen.getByRole('button', { name: 'Open PDF' })).toBeDisabled()
    expect(screen.getByRole('columnheader', { name: 'Jan' })).toBeInTheDocument()
  })
})

describe('other kinds', () => {
  it('renders HTML in a sandboxed iframe at the content URL', async () => {
    use(doc({ mime_type: 'text/html', name: 'a.html' }), fileRow({ kind: 'html', mime_type: 'text/html' }), () => new HttpResponse('<p>x</p>', { headers: { 'Content-Type': 'text/html' } }))
    renderView()
    const frame = await screen.findByTitle(/source file/i)
    expect(frame.tagName).toBe('IFRAME')
    expect(frame).toHaveAttribute('sandbox', '')
    expect(frame).toHaveAttribute('src', '/api/files/9/content')
  })

  it('renders a CSV as a table', async () => {
    use(
      doc({ mime_type: 'text/csv', name: 'a.csv' }),
      fileRow({ kind: 'csv', mime_type: 'text/csv' }),
      () => new HttpResponse('Fund,Class\n"Alpha, Ltd",A\n', { headers: { 'Content-Type': 'text/csv' } }),
    )
    renderView()
    const pane = await screen.findByRole('table', { name: /source file/i })
    expect(within(pane).getByText('Alpha, Ltd')).toBeInTheDocument()
  })

  it('says preview is not available for .xlsx', async () => {
    use(doc({ mime_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', name: 'a.xlsx' }), fileRow({ kind: 'spreadsheet' }))
    renderView()
    expect(await screen.findByText(/preview not available/i)).toBeInTheDocument()
  })
})

afterEach(() => vi.useRealTimers())

describe('readable links', () => {
  it('settles a bare id link on the readable one and keeps the query string', async () => {
    use(doc())
    renderView('/documents/5?tab=x')
    await waitFor(() => expect(screen.getByTestId('here')).toHaveTextContent('/documents/5-man-ahl-factsheet-2026-08?tab=x'))
    expect(screen.getByRole('heading', { name: 'man-ahl_factsheet_2026-08.pdf' })).toBeInTheDocument()
  })

  it('opens a readable link without redirecting, and corrects a stale name', async () => {
    use(doc())
    renderView('/documents/5-old-name')
    await waitFor(() => expect(screen.getByTestId('here')).toHaveTextContent('/documents/5-man-ahl-factsheet-2026-08'))
  })
})

describe('review fixes', () => {
  it('links to Drive', async () => {
    use(doc())
    renderView()
    const link = await screen.findByRole('link', { name: /open in google drive/i })
    expect(link).toHaveAttribute('href', 'https://drive.google.com/file/d/drv9/view')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'))
  })

  it('does not carry "gone" over to the next document', async () => {
    server.use(
      http.get('/api/documents/5', () => HttpResponse.json(doc())),
      http.get('/api/documents/6', () => HttpResponse.json(doc({ id: 6, source_file_id: 10, file: fileRow({ id: 10 }) }))),
      http.get('/api/files/9/content', () => HttpResponse.json({ detail: 'No longer in Drive' }, { status: 404 })),
      http.get('/api/files/10/content', () => new HttpResponse(new Uint8Array([1]), { headers: { 'Content-Type': 'application/pdf' } })),
    )
    const user = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/documents/5']}>
        <QueryProvider retry={false}>
          <Routes>
            <Route path="/documents/:id" element={<><DocumentView /><Link to="/documents/6">next</Link></>} />
          </Routes>
        </QueryProvider>
      </MemoryRouter>,
    )
    expect((await screen.findAllByText('No longer in Drive')).length).toBeGreaterThan(0)
    await user.click(screen.getByRole('link', { name: 'next' }))
    expect(await screen.findByRole('link', { name: 'Open PDF' })).toBeInTheDocument()
    expect(screen.queryByText('No longer in Drive')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /re-extract/i })).toBeEnabled()
  })

  it('polls every 3 s while queued, then stops; Re-extract cannot be double-posted', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    let status = 'done'
    let posts = 0
    let gets = 0
    server.use(
      http.get('/api/documents/5', () => {
        gets++
        return HttpResponse.json(doc({ status, file: fileRow({ status }) }))
      }),
      http.get('/api/files/9/content', () => new HttpResponse(new Uint8Array([1]), { headers: { 'Content-Type': 'application/pdf' } })),
      http.post('/api/files/9/reextract', () => {
        posts++
        status = 'queued'
        return HttpResponse.json({ id: 9, status })
      }),
    )
    renderView()
    const btn = await screen.findByRole('button', { name: /re-extract/i })
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    await user.click(btn)
    await user.click(btn)
    expect(await screen.findByText('Queued')).toBeInTheDocument()
    expect(posts).toBe(1)
    const before = gets
    status = 'done'
    await act(async () => { await vi.advanceTimersByTimeAsync(3100) })
    await waitFor(() => expect(screen.getByText('Done')).toBeInTheDocument())
    expect(gets).toBeGreaterThan(before)
    const settled = gets
    await act(async () => { await vi.advanceTimersByTimeAsync(10000) })
    expect(gets).toBe(settled)
  })
})

describe('large documents', () => {
  it('caps a long printed table', async () => {
    use(
      doc({
        funds: [{ name: 'TSP', share_class: 'G Fund' }],
        tables: [
          {
            index: 0,
            title: 'Share prices',
            header: [['Date', 'G Fund'], ['', 'USD']],
            rows: Array.from({ length: 200 }, (_, i) => [`d${i}`, '13.20']),
            rows_total: 5846,
          },
        ],
        rows_total: 5846,
      }),
    )
    renderView()
    expect(await screen.findByText('TSP (G Fund)')).toBeInTheDocument()
    const thead = screen.getByRole('columnheader', { name: 'Date' }).closest('thead')!
    expect(within(thead).getAllByRole('row')).toHaveLength(2)
    expect(within(thead).getByRole('columnheader', { name: 'USD' })).toBeInTheDocument()
    expect(screen.getByText('Showing first 200 of 5,846 rows.')).toBeInTheDocument()
  })

  it('shows no cap note when everything fits', async () => {
    use(doc())
    renderView()
    await screen.findByRole('heading', { name: /man-ahl/ })
    expect(screen.queryByText(/showing first/i)).not.toBeInTheDocument()
  })
})
