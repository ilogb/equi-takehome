/** /documents/:id: the source file beside tabbed extraction (As printed, Common rows). States D1-D6. */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronLeft, ExternalLink, RefreshCw, Tag } from 'lucide-react'
import { useCallback, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { DiffMarker, ReviewMarker } from '@/components/Markers'
import { SourceViewer } from '@/components/SourceViewer'
import { FileTypeIcon } from '@/components/FileTypeIcon'
import { StatusBadge } from '@/components/StatusBadge'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { api, fundLabel, keys, type DataRow, type DocumentDetail, type DocumentTable } from '@/lib/api'
import { formatMoney, formatPercent } from '@/lib/format'
import { cn } from '@/lib/utils'

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const PERCENT_MEASURES = new Set(['return', 'benchmark_return', 'account_return'])
const MEASURE_LABEL: Record<string, string> = {
  return: 'Return',
  benchmark_return: 'Benchmark return',
  aum: 'AUM',
  nav: 'NAV',
  account_value: 'Account value',
  account_return: 'Account return',
}

function periodLabel(r: DataRow): string {
  const [y, m] = r.period_end.split('-')
  if (r.period_kind === 'month') return `${MONTHS[Number(m) - 1]} ${y}`
  return r.period_kind === 'other' ? r.period_end : `${r.period_kind.toUpperCase()} to ${r.period_end}`
}

function valueText(r: DataRow): string {
  if (!PERCENT_MEASURES.has(r.measure)) return formatMoney(r.value, r.currency)
  const text = formatPercent(r.value)
  return r.value.trim().startsWith('-') || /^[+]?0*\.?0*$/.test(r.value.trim()) ? text : `+${text}`
}

function PrintedTables({
  tables,
  statement,
  picked,
  setPicked,
}: {
  tables: DocumentTable[]
  statement: boolean
  picked: number
  setPicked: (i: number) => void
}) {
  if (tables.length === 0) return <p className="text-sm text-muted-foreground">No tables were extracted from this file.</p>
  const t = tables.find((x) => x.index === picked) ?? tables[0]
  const holdings = statement && /holding/i.test(t.title ?? '')
  return (
    <div className="space-y-3">
      <div role="group" aria-label="Printed tables" className="flex flex-wrap gap-1.5">
        {tables.map((x) => (
          <Button
            key={x.index}
            size="sm"
            variant={x.index === t.index ? 'secondary' : 'outline'}
            className="h-7 px-2.5 text-xs"
            aria-pressed={x.index === t.index}
            onClick={() => setPicked(x.index)}
          >
            {x.title ?? `Table ${x.index + 1}`}
          </Button>
        ))}
      </div>
      {holdings && (
        <p className="text-xs text-muted-foreground">
          Per-holding gains are not fund returns, so this table is kept as printed and none of it becomes common rows.
        </p>
      )}
      <div className="overflow-auto rounded-lg border">
        <table className="w-full border-collapse text-xs">
          <thead>
            {t.header.map((hr, i) => (
              <tr key={i} className="border-b bg-muted/50 text-left">
                {hr.map((h, j) => (
                  <th key={j} scope="col" className="whitespace-nowrap px-2 py-1.5 font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {t.rows.map((r, i) => (
              <tr key={i} className="border-b last:border-0">
                {r.map((c, j) => (
                  <td key={j} className="whitespace-nowrap px-2 py-1 tabular-nums">
                    {c}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {t.rows_total > t.rows.length && (
        <p className="text-xs text-muted-foreground">
          Showing first {t.rows.length.toLocaleString('en-US')} of {t.rows_total.toLocaleString('en-US')} rows.
        </p>
      )}
    </div>
  )
}

function CommonRows({
  rows,
  total,
  documentId,
  statement,
}: {
  rows: DataRow[]
  total: number
  documentId: number
  statement: boolean
}) {
  const anyReview = rows.some((r) => r.needs_review)
  const anyDiff = rows.some((r) => r.conflict)
  if (rows.length === 0) return <p className="text-sm text-muted-foreground">No common rows were extracted from this file.</p>
  return (
    <div className="space-y-3">
      {statement && (
        <p className="text-xs text-muted-foreground">
          Account value and account return are kept apart from fund returns.
        </p>
      )}
      {(anyReview || anyDiff) && (
        <div className="space-y-1 text-xs text-muted-foreground">
          {anyReview && (
            <p className="flex items-center gap-1.5">
              <ReviewMarker /> marks a value the extractor was not sure about; the reason is shown beside it.
            </p>
          )}
          {anyDiff && (
            <p className="flex items-center gap-1.5">
              <DiffMarker /> marks a value that another current document reports differently.
            </p>
          )}
        </div>
      )}
      <div className="overflow-auto rounded-lg border">
        <table className="w-full border-collapse text-xs">
          <thead>
            <tr className="border-b bg-muted/50 text-left">
              {['Fund', 'Class', 'Period', 'Measure', 'Value', 'Printed as', 'Ccy'].map((h) => (
                <th key={h} scope="col" className={cn('whitespace-nowrap px-2 py-1.5 font-medium', h === 'Value' && 'text-right')}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-b align-top last:border-0">
                <td className="px-2 py-1">{r.entity}</td>
                <td className="px-2 py-1">{r.share_class}</td>
                <td className="whitespace-nowrap px-2 py-1 tabular-nums">{periodLabel(r)}</td>
                <td className="px-2 py-1">{MEASURE_LABEL[r.measure] ?? r.measure}</td>
                <td className="px-2 py-1 text-right tabular-nums">
                  <span className="inline-flex items-center justify-end gap-1.5">
                    {r.needs_review && <ReviewMarker reason={r.review_reason} />}
                    {r.conflict && <DiffMarker />}
                    <span className={cn(r.value.trim().startsWith('-') && 'text-negative')}>{valueText(r)}</span>
                  </span>
                  {r.needs_review && r.review_reason && (
                    <div className="mt-0.5 text-[11px] text-warning">{r.review_reason}</div>
                  )}
                </td>
                <td className="px-2 py-1 tabular-nums text-muted-foreground">{r.value_as_written}</td>
                <td className="px-2 py-1">{r.currency}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {total > rows.length && (
        <p className="text-xs text-muted-foreground">
          Showing {rows.length.toLocaleString('en-US')} of {total.toLocaleString('en-US')} —{' '}
          <Link to={`/data?document_id=${documentId}`} className="text-primary hover:underline">
            see all in Data
          </Link>
        </p>
      )}
    </div>
  )
}

function Meta({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-sm">{value || '—'}</dd>
    </div>
  )
}

const PENDING = new Set(['queued', 'processing'])
const POLL_MS = 3_000

/** Keyed on the route id so per-document state (like "gone from Drive") never leaks across documents. */
export function DocumentView() {
  const { id } = useParams()
  return <DocumentBody key={id} id={Number(id)} />
}

function DocumentBody({ id }: { id: number }) {
  const qc = useQueryClient()
  const doc = useQuery({
    queryKey: keys.document(id),
    queryFn: () => api.document(id),
    enabled: Number.isFinite(id),
    refetchInterval: (q) => (q.state.data && PENDING.has(q.state.data.file.status) ? POLL_MS : false),
  })
  const [gone, setGone] = useState(false)
  const [picked, setPicked] = useState(0)
  const onMissing = useCallback(() => setGone(true), [])
  const fileId = doc.data?.source_file_id
  const afterAction = () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: keys.document(id) }),
      qc.invalidateQueries({ queryKey: ['files'] }),
      qc.invalidateQueries({ queryKey: keys.folder }),
    ])
  const reextract = useMutation({ mutationFn: () => api.reextractFile(fileId!), onSuccess: afterAction })
  const retry = useMutation({ mutationFn: () => api.retryFile(fileId!), onSuccess: afterAction })

  if (doc.isError) {
    return (
      <section className="mx-auto max-w-[1480px] space-y-3 px-4 py-6">
        <Link to="/library" className="text-sm text-muted-foreground hover:underline">Library</Link>
        <p role="alert" className="text-sm text-negative">Could not load this document.</p>
      </section>
    )
  }
  if (!doc.data) return <p className="p-8 text-sm text-muted-foreground">Loading…</p>

  const d: DocumentDetail = doc.data
  const file = d.file
  const missing = gone || file.missing_in_drive
  const statement = (d.doc_type ?? '').toLowerCase() === 'statement'
  const canReextract = d.status === 'done' || d.status === 'needs_review'
  const driveUrl = `https://drive.google.com/file/d/${file.drive_file_id}/view`
  const driveLabel = (
    <>
      <ExternalLink aria-hidden />
      Open in Google Drive
    </>
  )

  return (
    <section className="mx-auto max-w-[1480px] space-y-4 px-4 py-6">
      <header className="space-y-3">
        <Link to="/library" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:underline">
          <ChevronLeft className="size-3.5" aria-hidden />
          Library
        </Link>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2">
            <FileTypeIcon kind={file.kind} />
            <h1 className="truncate text-xl font-semibold tracking-tight">{d.name}</h1>
            <StatusBadge status={d.status} />
          </div>
          <div className="flex items-center gap-2">
            {canReextract && (
              <Button size="sm" variant="outline" disabled={missing || reextract.isPending} onClick={() => reextract.mutate()}>
                <RefreshCw aria-hidden />
                Re-extract
              </Button>
            )}
            {missing ? (
              <Button size="sm" variant="outline" disabled>
                {driveLabel}
              </Button>
            ) : (
              <Button asChild size="sm" variant="outline">
                <a href={driveUrl} target="_blank" rel="noopener noreferrer">
                  {driveLabel}
                </a>
              </Button>
            )}
          </div>
        </div>
        {reextract.isError && <p role="alert" className="text-sm text-negative">Could not start re-extraction. Try again.</p>}
        <dl className="grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-3 lg:grid-cols-5">
          <Meta label="Doc type" value={d.doc_type} />
          <Meta label="Manager" value={d.manager} />
          <Meta label="As of" value={d.as_of_date} />
          <Meta label="Currency" value={d.currency} />
          <Meta label="Path" value={d.path} />
        </dl>
        {d.funds.length > 0 && (
          <ul className="flex flex-wrap gap-x-4 text-sm">
            {d.funds.map((f, i) => (
              <li key={i}>{fundLabel(f)}</li>
            ))}
          </ul>
        )}
        {d.tags.length > 0 && (
          <div className="flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
            <Tag className="size-3 shrink-0" aria-hidden />
            {d.tags.map((t) => (
              <span key={t}>{t}</span>
            ))}
          </div>
        )}
      </header>

      {d.status === 'failed' && (
        <Alert variant="destructive">
          <AlertTitle>Extraction failed</AlertTitle>
          <AlertDescription className="space-y-2">
            <p>{file.error ?? 'The file could not be processed.'}</p>
            <Button size="sm" variant="destructive" disabled={retry.isPending} onClick={() => retry.mutate()}>
              Retry
            </Button>
            {retry.isError && <p>Could not retry. Try again.</p>}
          </AlertDescription>
        </Alert>
      )}
      {d.status === 'scanned_no_text' && (
        <Alert>
          <AlertTitle>Scanned: no text</AlertTitle>
          <AlertDescription className="space-y-1">
            <p>
              The pages of this PDF are images with no text layer. This version doesn’t read scanned pages, so no
              metadata, tables or common rows were extracted, and Simple search can’t find its contents.
            </p>
            <p>If you have a text PDF, CSV, .xlsx or email with the same figures, add it to the folder and it will be picked up within a minute.</p>
          </AlertDescription>
        </Alert>
      )}
      {d.status === 'unsupported' && (
        <Alert>
          <AlertTitle>Unsupported</AlertTitle>
          <AlertDescription>{file.error ?? 'This file is not supported, so nothing was extracted.'}</AlertDescription>
        </Alert>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <SourceViewer
          fileId={d.source_file_id}
          mimeType={d.mime_type}
          name={d.name}
          path={d.path}
          missing={missing}
          onMissing={onMissing}
        />
        <Tabs defaultValue="printed" className="min-w-0">
          <TabsList>
            <TabsTrigger value="printed">
              As printed <span className="text-xs tabular-nums text-muted-foreground">{d.tables.length}</span>
            </TabsTrigger>
            <TabsTrigger value="rows">
              Common rows <span className="text-xs tabular-nums text-muted-foreground">{d.rows_total.toLocaleString('en-US')}</span>
            </TabsTrigger>
          </TabsList>
          <TabsContent value="printed">
            <PrintedTables tables={d.tables} statement={statement} picked={picked} setPicked={setPicked} />
          </TabsContent>
          <TabsContent value="rows">
            <CommonRows rows={d.rows} total={d.rows_total} documentId={d.id} statement={statement} />
          </TabsContent>
        </Tabs>
      </div>
    </section>
  )
}
