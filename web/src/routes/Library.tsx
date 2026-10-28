/** /library: every synced file with status, metadata, tags and path; sync controls and reconnect handling (L1-L4). */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ExternalLink, RefreshCw, Tag } from 'lucide-react'
import { useEffect } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { FileTypeIcon } from '@/components/FileTypeIcon'
import { LibraryDashboard } from '@/components/LibraryDashboard'
import { FILE_STATUSES, StatusBadge, type FileStatus } from '@/components/StatusBadge'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { api, ApiError, folderQuery, fundLabel, keys, urls, useSyncNow, type FileRow } from '@/lib/api'
import { relativeTime } from '@/components/SyncPill'
import { documentPath } from '@/lib/paths'
import { cn } from '@/lib/utils'

const POLL_MS = 5_000
const STATUS_LABEL: Record<FileStatus, string> = {
  queued: 'queued',
  processing: 'processing',
  done: 'done',
  needs_review: 'need review',
  failed: 'failed',
  unsupported: 'unsupported',
  scanned_no_text: 'scanned',
}

function exactTime(iso: string): string {
  return new Date(iso).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })
}

/** Path relative to the folder, minus the file name; empty at the folder root. */
function parentPath(path: string): string {
  const i = path.lastIndexOf('/')
  return i < 0 ? '' : path.slice(0, i)
}

function FileRowView({ f, onOpen }: { f: FileRow; onOpen: (() => void) | null }) {
  const qc = useQueryClient()
  const retry = useMutation({
    mutationFn: () => api.retryFile(f.id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['files'] })
      void qc.invalidateQueries({ queryKey: keys.folder })
    },
  })
  const dir = parentPath(f.path)
  return (
    <tr className={cn('border-b align-top hover:bg-muted/40', onOpen && 'cursor-pointer')} onClick={onOpen ?? undefined}>
      <td className="px-3 py-2.5">
        <div className="flex min-w-0 items-start gap-2">
          <FileTypeIcon kind={f.kind} className="mt-0.5" />
          <div className="min-w-0 space-y-0.5">
            {f.document_id != null ? (
              <Link
                to={documentPath(f.document_id, f.name)}
                className="font-medium hover:underline"
                onClick={(e) => e.stopPropagation()}
              >
                {f.name}
              </Link>
            ) : (
              <span className="font-medium">{f.name}</span>
            )}
            {dir && <div className="text-xs text-muted-foreground">{dir}</div>}
            {f.status === 'failed' && f.error && <div className="text-xs text-negative">{f.error}</div>}
            {f.tags.length > 0 && (
              <div className="flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
                <Tag className="size-3 shrink-0" aria-hidden />
                {f.tags.map((t) => (
                  <span key={t}>{t}</span>
                ))}
              </div>
            )}
          </div>
        </div>
      </td>
      <td className="px-3 py-2.5">{f.doc_type}</td>
      <td className="px-3 py-2.5">{f.manager}</td>
      <td className="px-3 py-2.5">
        {f.funds.map((fund, i) => (
          <div key={i}>{fundLabel(fund)}</div>
        ))}
      </td>
      <td className="px-3 py-2.5 tabular-nums">{f.as_of_date}</td>
      <td className="px-3 py-2.5 text-right tabular-nums">{f.row_count > 0 ? f.row_count.toLocaleString('en-US') : '—'}</td>
      <td className="px-3 py-2.5">
        <div className="flex items-center gap-2">
          <StatusBadge status={f.status} />
          {f.status === 'failed' && (
            <Button
              size="sm"
              variant="outline"
              className="h-6 px-2 text-xs"
              disabled={retry.isPending}
              onClick={(e) => {
                e.stopPropagation()
                retry.mutate()
              }}
            >
              Retry
            </Button>
          )}
        </div>
        {retry.isError && <p role="alert" className="mt-1 text-xs text-negative">Could not retry. Try again.</p>}
      </td>
      <td className="whitespace-nowrap px-3 py-2.5 text-muted-foreground">
        <span title={exactTime(f.updated_at)}>{relativeTime(f.updated_at)}</span>
      </td>
    </tr>
  )
}

export function Library() {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const raw = params.get('status')
  const status = FILE_STATUSES.find((s) => s === raw)
  const setStatus = (next: FileStatus | undefined) =>
    setParams(
      (p) => {
        const n = new URLSearchParams(p)
        if (next) n.set('status', next)
        else n.delete('status')
        return n
      },
      { replace: false },
    )
  const folder = useQuery(folderQuery())
  const noFolder = folder.error instanceof ApiError && folder.error.status === 404
  useEffect(() => {
    if (noFolder) navigate('/connect', { replace: true })
  }, [noFolder, navigate])
  const counts = folder.data?.counts_by_status ?? {}
  const pending = (counts.queued ?? 0) + (counts.processing ?? 0) > 0
  const filters = { status }
  const files = useQuery({
    queryKey: keys.files(filters),
    queryFn: () => api.files(filters),
    refetchInterval: (q) =>
      pending || q.state.data?.some((r) => r.status === 'queued' || r.status === 'processing') ? POLL_MS : false,
  })
  const sync = useSyncNow()
  const openDocument = (id: number, name: string) => () => navigate(documentPath(id, name))
  const folderFailed = folder.isError && !noFolder
  const needsReconnect = folder.data?.needs_reconnect ?? false
  const total = Object.values(counts).reduce((a, b) => a + (b ?? 0), 0)
  const rows = files.data ?? []
  const syncDisabled = pending || needsReconnect || sync.isPending || folderFailed || !folder.data
  const lastSynced = folder.data?.last_synced_at ? exactTime(folder.data.last_synced_at) : null

  return (
    <section className="mx-auto max-w-[1480px] space-y-5 px-4 py-6">
      {needsReconnect && (
        <Alert variant="destructive">
          <AlertTitle>Google Drive access was removed, so sync has stopped.</AlertTitle>
          <AlertDescription className="space-y-3">
            <p>
              {lastSynced ? `Last synced ${lastSynced}. ` : ''}Documents already processed are still here and
              searchable. Opening a file needs access again, because files are streamed from Drive.
            </p>
            <Button asChild size="sm" variant="destructive">
              <a href={urls.googleStart}>Reconnect Google Drive</a>
            </Button>
          </AlertDescription>
        </Alert>
      )}

      {folderFailed && (
        <Alert variant="destructive">
          <AlertTitle>Could not load the folder status.</AlertTitle>
          <AlertDescription>Check your connection and try again in a moment.</AlertDescription>
        </Alert>
      )}

      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Library</h1>
          <p className="text-sm text-muted-foreground">
            {folder.data
              ? `${total} ${total === 1 ? 'file' : 'files'} in ${folder.data.name}${
                  needsReconnect ? ' · not syncing' : ' · checks for changes every 60 s'
                }`
              : ' '}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {folder.data && (
            <Button asChild size="sm" variant="outline">
              <a
                href={`https://drive.google.com/drive/folders/${folder.data.drive_folder_id}`}
                target="_blank"
                rel="noopener noreferrer"
              >
                <ExternalLink aria-hidden />
                Open folder in Drive
              </a>
            </Button>
          )}
          <Button size="sm" disabled={syncDisabled} onClick={() => sync.mutate()}>
            <RefreshCw className={cn(pending && 'animate-spin')} aria-hidden />
            Sync now
          </Button>
        </div>
      </div>
      {sync.isError && (
        <p role="alert" className="text-sm text-negative">
          Could not start a sync. Try again.
        </p>
      )}

      {total > 0 && <LibraryDashboard />}

      {total > 0 && (
        <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Filter by status">
          <Button
            size="sm"
            variant={status === undefined ? 'secondary' : 'ghost'}
            className="h-7 px-2.5 text-xs"
            aria-pressed={status === undefined}
            onClick={() => setStatus(undefined)}
          >
            All {total}
          </Button>
          {FILE_STATUSES.filter((s) => (counts[s] ?? 0) > 0).map((s) => (
            <Button
              key={s}
              size="sm"
              variant={status === s ? 'secondary' : 'ghost'}
              className="h-7 gap-1.5 px-2.5 text-xs"
              aria-pressed={status === s}
              onClick={() => setStatus(status === s ? undefined : s)}
            >
              <span className="font-semibold tabular-nums">{counts[s]}</span>
              {STATUS_LABEL[s]}
            </Button>
          ))}
        </div>
      )}

      {files.isError && <p role="alert" className="text-sm text-negative">Could not load files.</p>}

      <div className="overflow-x-auto rounded-xl border bg-background">
        <table className="w-full min-w-[1100px] border-collapse text-sm">
          <thead>
            <tr className="border-b text-left text-xs text-muted-foreground">
              {['File', 'Doc type', 'Manager', 'Fund or account', 'As of', 'Data points', 'Status', 'Synced'].map((h) => (
                <th key={h} scope="col" className={cn('px-3 py-2 font-medium', h === 'Data points' && 'text-right')}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((f) => (
              <FileRowView
                key={f.id}
                f={f}
                onOpen={f.document_id != null ? openDocument(f.document_id, f.name) : null}
              />
            ))}
            {files.isSuccess && rows.length === 0 && !folderFailed && (
              <tr>
                <td colSpan={8} className="px-3 py-10 text-center">
                  {status ? (
                    <p className="text-muted-foreground">No files with this status.</p>
                  ) : (
                    <div className="mx-auto max-w-lg space-y-3">
                      <p className="font-medium">No documents the app can read yet</p>
                      <p className="text-muted-foreground">
                        Add PDF, CSV, Excel (.xlsx), HTML or .eml files to the folder or its subfolders. They appear
                        here within a minute.
                      </p>
                      <Button asChild variant="outline" size="sm">
                        <Link to="/connect">Choose a different folder</Link>
                      </Button>
                    </div>
                  )}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  )
}
