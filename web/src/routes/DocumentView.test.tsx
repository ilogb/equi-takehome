import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { QueryProvider } from '@/QueryProvider'
import { server } from '@/test/server'
import { DocumentView } from './DocumentView'

vi.mock('react-pdf', async () => {
  const React = await import('react')
  return {
    pdfjs: { GlobalWorkerOptions: {} },
    Document: ({ file, onLoadSuccess, children }: { file: { data: ArrayBuffer }; onLoadSuccess: (d: { numPages: number }) => void; children: React.ReactNode }) => {
      React.useEffect(() => onLoadSuccess({ numPages: 4 }), [onLoadSuccess])
      return <div data-testid="pdf" data-bytes={file.data.byteLength}>{children}</div>
    },
    Page: ({ pageNumber }: { pageNumber: number }) => <div data-testid="pdf-page">page {pageNumber}</div>,
  }
})

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

const doc = (over: object = {}) => ({
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
  funds: ['Man AHL Diversified'],
  tables: [
    { index: 0, title: 'Historical Performance', header: ['Year', 'Jan'], rows: [['2026', '8.42%']] },
    { index: 1, title: 'Cumulative Performance', header: ['Period', 'Return'], rows: [['1y', '9.10%']] },
  ],
  rows: [
    row(),
    row({ id: 2, period_end: '2026-02-28', value: '-0.0375', value_as_written: '(3.75%)', needs_review: true, review_reason: 'footnote 2 says restated' }),
    row({ id: 3, period_end: '2026-03-31', value: '0.0512', value_as_written: '5.12%', conflict: true }),
    row({ id: 4, measure: 'aum', period_kind: 'other', period_end: '2026-08-31', value: '24963108.45', value_as_written: '24,963,108.45', unit: 'currency' }),
  ],
  ...over,
})

const fileRow = (over: object = {}) => ({
  id: 9,
  name: 'man-ahl_factsheet_2026-08.pdf',
  path: 'Factsheets/man-ahl_factsheet_2026-08.pdf',
  mime_type: 'application/pdf',
  kind: 'pdf',
  status: 'done',
  error: null,
  missing_in_drive: false,
  doc_type: 'Factsheet',
  manager: 'Man AHL',
  funds: [],
  as_of_date: null,
  tags: [],
  row_count: 4,
  updated_at: '2026-10-28T10:42:00Z',
  ...over,
})

function use(d: object, f: object = fileRow(), content?: () => Response) {
  server.use(
    http.get('/api/documents/5', () => HttpResponse.json(d)),
    http.get('/api/files', () => HttpResponse.json([f])),
    http.get('/api/files/9/content', content ?? (() => new HttpResponse(new Uint8Array([1, 2, 3]), { headers: { 'Content-Type': 'application/pdf' } }))),
  )
}

function renderView() {
  return render(
    <MemoryRouter initialEntries={['/documents/5']}>
      <QueryProvider retry={false}>
        <Routes>
          <Route path="/documents/:id" element={<DocumentView />} />
          <Route path="/library" element={<div>library page</div>} />
        </Routes>
      </QueryProvider>
    </MemoryRouter>,
  )
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
    const pdf = await screen.findByTestId('pdf')
    expect(pdf).toHaveAttribute('data-bytes', '3')
    expect(await screen.findByText(/page 1 of 4/i)).toBeInTheDocument()
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

  it('Common rows shows formatted values, printed-as text and markers', async () => {
    const user = userEvent.setup()
    use(doc())
    renderView()
    await user.click(await screen.findByRole('tab', { name: /common rows/i }))
    expect(screen.getByText('+8.42%')).toBeInTheDocument()
    expect(screen.getByText('−3.75%')).toBeInTheDocument()
    expect(screen.getByText('(3.75%)')).toBeInTheDocument()
    expect(screen.getByText('$24,963,108.45')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /needs review: footnote 2 says restated/i })).toBeInTheDocument()
    expect(screen.getAllByRole('img', { name: 'Sources differ' })).toHaveLength(2)
    expect(screen.getByText('Jan 2026')).toBeInTheDocument()
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
  it('explains the markers in the Common rows tab', async () => {
    const user = userEvent.setup()
    use(doc({ status: 'needs_review' }))
    renderView()
    expect(await screen.findByText('Needs review')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /re-extract/i })).toBeEnabled()
    await user.click(screen.getByRole('tab', { name: /common rows/i }))
    expect(screen.getByText(/marks a value the extractor was not sure about/i)).toBeInTheDocument()
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
    expect(await screen.findByTestId('pdf')).toBeInTheDocument()
  })
})

describe('D4 statement', () => {
  it('explains account measures and the holdings table', async () => {
    const user = userEvent.setup()
    use(
      doc({
        doc_type: 'Statement',
        tables: [{ index: 0, title: 'Holdings', header: ['Holding', 'Gain'], rows: [['Man AHL', '4.1%']] }],
        rows: [row({ measure: 'account_value', period_kind: 'other', value: '1000.5', value_as_written: '1,000.50' })],
      }),
    )
    renderView()
    expect(await screen.findByText(/per-holding gains are not fund returns/i)).toBeInTheDocument()
    await user.click(screen.getByRole('tab', { name: /common rows/i }))
    expect(screen.getByText(/account value and account return are kept apart from fund returns/i)).toBeInTheDocument()
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
    const user = userEvent.setup()
    use(doc(), fileRow(), () => HttpResponse.json({ detail: 'No longer in Drive' }, { status: 404 }))
    renderView()
    expect(await screen.findByText('No longer in Drive')).toBeInTheDocument()
    expect(screen.getByText(/last known at/i)).toBeInTheDocument()
    expect(screen.getAllByText('Factsheets/man-ahl_factsheet_2026-08.pdf').length).toBeGreaterThan(0)
    await waitFor(() => expect(screen.getByRole('button', { name: /re-extract/i })).toBeDisabled())
    expect(screen.getByRole('columnheader', { name: 'Jan' })).toBeInTheDocument()
    await user.click(screen.getByRole('tab', { name: /common rows/i }))
    expect(screen.getByText('+8.42%')).toBeInTheDocument()
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
