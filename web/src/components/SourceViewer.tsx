/** Left pane of the document view: the original file, streamed from Drive via /api/files/{id}/content. */
import { useEffect, useMemo } from 'react'
import { ApiError, urls } from '@/lib/api'
import { useContent } from '@/lib/fileContent'

export type ViewerKind = 'pdf' | 'csv' | 'frame' | 'spreadsheet' | 'other'

/** Mirrors the backend's file_kind, with .eml and HTML both shown in a sandboxed frame. */
export function viewerKind(mimeType: string, name: string): ViewerKind {
  const lowered = name.toLowerCase()
  const mime = mimeType.split(';')[0].trim().toLowerCase()
  if (mime === 'application/pdf' || lowered.endsWith('.pdf')) return 'pdf'
  if (mime === 'text/csv' || lowered.endsWith('.csv')) return 'csv'
  if (mime === 'text/html' || mime === 'message/rfc822' || /\.(html?|eml)$/.test(lowered)) return 'frame'
  if (mime.includes('spreadsheet') || mime.includes('excel') || /\.xlsx?$/.test(lowered)) return 'spreadsheet'
  return 'other'
}

/** RFC 4180-style parser: quoted fields, doubled quotes, CRLF. */
export function parseCsv(text: string): string[][] {
  const rows: string[][] = []
  let row: string[] = []
  let field = ''
  let quoted = false
  for (let i = 0; i < text.length; i++) {
    const c = text[i]
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') {
        field += '"'
        i++
      } else if (c === '"') quoted = false
      else field += c
    } else if (c === '"') quoted = true
    else if (c === ',') {
      row.push(field)
      field = ''
    } else if (c === '\n' || c === '\r') {
      if (c === '\r' && text[i + 1] === '\n') i++
      row.push(field)
      rows.push(row)
      row = []
      field = ''
    } else field += c
  }
  if (field !== '' || row.length > 0) {
    row.push(field)
    rows.push(row)
  }
  return rows
}

function Note({ children }: { children: React.ReactNode }) {
  return <p className="p-6 text-sm text-muted-foreground">{children}</p>
}

function CsvPane({ fileId, onMissing }: { fileId: number; onMissing: () => void }) {
  const content = useContent(fileId, 'text', true)
  useEffect(() => {
    if (content.error instanceof ApiError && content.error.status === 404) onMissing()
  }, [content.error, onMissing])
  const rows = useMemo(() => (typeof content.data === 'string' ? parseCsv(content.data) : []), [content.data])
  if (content.isError) return <Note>Could not load the file.</Note>
  if (content.isPending) return <Note>Loading…</Note>
  return (
    <div className="min-h-0 flex-1 overflow-auto">
      <table aria-label="Source file" className="w-full border-collapse text-xs">
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b">
              <th scope="row" className="sticky left-0 bg-muted px-2 py-1 text-right font-normal text-muted-foreground">
                {i + 1}
              </th>
              {r.map((cell, j) => (
                <td key={j} className="whitespace-nowrap px-2 py-1">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function FramePane({ fileId, onMissing }: { fileId: number; onMissing: () => void }) {
  // The frame itself cannot report a 404, so ask first (the body is not downloaded).
  const probe = useContent(fileId, 'probe', true)
  useEffect(() => {
    if (probe.error instanceof ApiError && probe.error.status === 404) onMissing()
  }, [probe.error, onMissing])
  if (probe.isError) return <Note>Could not load the file.</Note>
  if (probe.isPending) return <Note>Loading…</Note>
  // sandbox="" grants nothing: no scripts, no same-origin, no forms.
  return <iframe title="Source file" sandbox="" src={urls.fileContent(fileId)} className="min-h-0 w-full flex-1 bg-white" />
}

export function SourceViewer({
  fileId,
  mimeType,
  name,
  path,
  missing,
  onMissing,
}: {
  fileId: number
  mimeType: string
  name: string
  path: string
  missing: boolean
  onMissing: () => void
}) {
  const kind = viewerKind(mimeType, name)
  let body: React.ReactNode
  if (missing) {
    body = (
      <div className="space-y-3 p-6 text-sm">
        <p className="font-medium">No longer in Drive</p>
        <p className="text-muted-foreground">
          This file was deleted or moved out of the folder, so it can’t be shown. The tables and data points
          extracted from it are kept and still used in Data and search.
        </p>
        <div>
          <div className="text-xs text-muted-foreground">Last known at</div>
          <div className="break-all font-mono text-xs">{path}</div>
        </div>
      </div>
    )
  } else if (kind === 'csv') body = <CsvPane fileId={fileId} onMissing={onMissing} />
  else if (kind === 'frame') body = <FramePane fileId={fileId} onMissing={onMissing} />
  else if (kind === 'spreadsheet') body = <Note>Preview not available — see Source tables.</Note>
  else body = <Note>Preview not available for this file type.</Note>
  return <div className="flex min-h-[480px] flex-col overflow-hidden rounded-xl border bg-background">{body}</div>
}
