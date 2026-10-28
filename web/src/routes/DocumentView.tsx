/** /documents/:id-:name (the id alone also works): the source file and the tables printed in it (Source tables). States D1-D6. */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronLeft, ExternalLink, FileText, RefreshCw, Tag } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { SourceViewer, viewerKind } from '@/components/SourceViewer'
import { FileTypeIcon } from '@/components/FileTypeIcon'
import { StatusBadge } from '@/components/StatusBadge'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { api, ApiError, fundLabel, keys, urls, type DocumentDetail, type DocumentTable } from '@/lib/api'
import { useContent } from '@/lib/fileContent'
import { documentIdFromParam, documentPath } from '@/lib/paths'
import { cn } from '@/lib/utils'

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
          Per-holding gains are not fund returns, so this table is kept as printed and none of it becomes data points.
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
  const id = documentIdFromParam(useParams().id)
  return <DocumentBody key={id} id={id} />
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
  // Old or hand-typed links (/documents/6, a stale name) settle on the readable one.
  const navigate = useNavigate()
  const location = useLocation()
  const canonical = doc.data ? documentPath(id, doc.data.name) : null
  useEffect(() => {
    if (canonical && location.pathname !== canonical) {
      navigate(`${canonical}${location.search}${location.hash}`, { replace: true })
    }
  }, [canonical, location.pathname, location.search, location.hash, navigate])
  // PDFs open in the browser's viewer from the header, so there is no pane to notice a file
  // gone from Drive: ask once (the body is not downloaded).
  const isPdf = doc.data ? viewerKind(doc.data.mime_type, doc.data.name) === 'pdf' : false
  const probe = useContent(fileId ?? 0, 'probe', isPdf && !doc.data?.file.missing_in_drive)
  const pdfGone = probe.error instanceof ApiError && probe.error.status === 404
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
  const missing = gone || pdfGone || file.missing_in_drive
  const showPane = !isPdf || missing
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
            {isPdf &&
              (missing ? (
                <Button size="sm" variant="outline" disabled>
                  <FileText aria-hidden />
                  Open PDF
                </Button>
              ) : (
                <Button asChild size="sm" variant="outline">
                  <a href={urls.fileContent(d.source_file_id)} target="_blank" rel="noopener noreferrer">
                    <FileText aria-hidden />
                    Open PDF
                  </a>
                </Button>
              ))}
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
              metadata, tables or data points were extracted, and Simple search can’t find its contents.
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

      {/* A PDF has no in-page preview (it opens from the header), so the extraction takes the
          full width; the pane stays when the file is gone, to say so. */}
      <div className={cn('grid gap-4', showPane && 'lg:grid-cols-2')}>
        {showPane && (
          <SourceViewer
            fileId={d.source_file_id}
            mimeType={d.mime_type}
            name={d.name}
            path={d.path}
            missing={missing}
            onMissing={onMissing}
          />
        )}
        <div className="min-w-0 space-y-3">
          <h2 className="text-sm font-semibold">
            Source tables <span className="text-xs font-normal tabular-nums text-muted-foreground">{d.tables.length}</span>
          </h2>
          <PrintedTables tables={d.tables} statement={statement} picked={picked} setPicked={setPicked} />
        </div>
      </div>
    </section>
  )
}
