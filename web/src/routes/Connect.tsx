/** /connect: sign in with Google (C1/C2), choose the Drive folder (C3), watch the first sync (C4). */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FileText, FolderOpen } from 'lucide-react'
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Progress } from '@/components/ui/progress'
import { api, ApiError, folderQuery, keys, urls, type FolderStatus, type Me } from '@/lib/api'

export const POLL_MS = 2000

const SIGN_IN_ERRORS: Record<string, string> = {
  access_denied: 'Google sign-in was cancelled.',
  auth_failed: 'Google sign-in failed. Try again.',
}

/** Files that reached an end state (unsupported files are listed by the library but not counted here). */
export function syncProgress(counts: FolderStatus['counts_by_status']) {
  const n = (k: keyof typeof counts) => counts[k] ?? 0
  const processed = n('done') + n('needs_review') + n('failed') + n('scanned_no_text')
  const pending = n('queued') + n('processing')
  return { processed, pending, total: processed + pending }
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 px-4 py-8">
      <div className="flex items-center gap-2">
        <span className="flex size-7 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm">
          <FileText className="size-4" aria-hidden />
        </span>
        <span className="font-semibold tracking-tight">Document Intelligence</span>
      </div>
      {children}
    </div>
  )
}

function SignedOut({ error }: { error: string | null }) {
  const notAllowed = error === 'not_allowed'
  const other = error && !notAllowed ? (SIGN_IN_ERRORS[error] ?? 'Something went wrong. Try again.') : null
  return (
    <Card className="w-full max-w-sm">
      <CardHeader>
        <CardTitle>Sign in</CardTitle>
        <CardDescription>
          Use the Google account that holds your fund documents. Only approved accounts can sign in.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {notAllowed && (
          <Alert variant="destructive">
            <AlertTitle>That Google account isn’t on the access list.</AlertTitle>
            <AlertDescription>Ask the app’s owner to add this address, then sign in again.</AlertDescription>
          </Alert>
        )}
        {other && (
          <Alert variant="destructive">
            <AlertDescription>{other}</AlertDescription>
          </Alert>
        )}
        {/* A full-page navigation: Google's consent screen cannot run inside fetch. */}
        <Button asChild variant="outline" className="w-full">
          <a href={urls.googleStart}>{notAllowed ? 'Use another Google account' : 'Continue with Google'}</a>
        </Button>
        {!notAllowed && (
          <p className="text-xs text-muted-foreground">
            The app asks for read-only access to Google Drive. It reads only the folder you choose next and keeps no
            copies of your files.
          </p>
        )}
      </CardContent>
    </Card>
  )
}

function FolderChooser({
  replacing,
  currentName,
  onChosen,
  onCancel,
}: {
  replacing: boolean
  currentName?: string
  onChosen: (status: FolderStatus) => void
  onCancel: () => void
}) {
  const [q, setQ] = useState('')
  const [selected, setSelected] = useState<string | null>(null)
  const [confirming, setConfirming] = useState(false)
  const folders = useQuery({
    queryKey: keys.folders(q),
    queryFn: () => api.searchFolders(q),
    placeholderData: keepPreviousData,
    meta: { handles401: true },
  })
  const choose = useMutation({ mutationFn: api.chooseFolder, onSuccess: onChosen })
  const chosen = folders.data?.find((f) => f.id === selected)

  function submit() {
    if (!selected) return
    if (replacing && !confirming) return setConfirming(true)
    setConfirming(false)
    choose.mutate(selected)
  }

  return (
    <Card className="w-full max-w-xl">
      <CardHeader>
        <CardTitle className="text-xl">Choose the folder with your fund documents</CardTitle>
        <CardDescription>
          The app reads PDF, CSV, Excel (.xlsx), HTML and .eml files in this folder and its subfolders. The rest of your
          Drive isn’t read. Files stay in Drive; the app keeps only what it extracts.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Input
          type="search"
          aria-label="Search your folders"
          placeholder="Search your folders"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <div role="radiogroup" aria-label="Folders" className="flex max-h-72 flex-col gap-1 overflow-y-auto">
          {folders.isError && <p className="text-sm text-muted-foreground">Could not load your folders.</p>}
          {folders.data?.length === 0 && <p className="text-sm text-muted-foreground">No folders match.</p>}
          {folders.data?.map((f) => (
            <label
              key={f.id}
              className="flex cursor-pointer items-center gap-3 rounded-md border px-3 py-2 text-sm has-[:checked]:border-primary has-[:checked]:bg-primary/5"
            >
              <input
                type="radio"
                name="folder"
                value={f.id}
                checked={selected === f.id}
                onChange={() => {
                  setSelected(f.id)
                  setConfirming(false)
                }}
              />
              <FolderOpen className="size-4 text-muted-foreground" aria-hidden />
              <span>{f.name}</span>
            </label>
          ))}
        </div>
        {choose.error && (
          <Alert variant="destructive">
            <AlertDescription>
              {choose.error instanceof ApiError ? choose.error.message : 'Could not use that folder. Try again.'}
            </AlertDescription>
          </Alert>
        )}
        {confirming && (
          <Alert variant="destructive" role="alertdialog" aria-label="Replace folder">
            <AlertTitle>Replace {currentName ? `“${currentName}”` : 'your current folder'}?</AlertTitle>
            <AlertDescription className="flex flex-col gap-3">
              <span>
                Changing folder removes everything extracted from the current one: documents, values and search data.
                The new folder is then read from scratch.
              </span>
              <span className="flex gap-2">
                <Button variant="destructive" size="sm" onClick={submit} disabled={choose.isPending}>
                  Replace folder
                </Button>
                <Button variant="outline" size="sm" onClick={() => setConfirming(false)}>
                  Cancel
                </Button>
              </span>
            </AlertDescription>
          </Alert>
        )}
        <div className="flex items-center justify-between gap-3">
          <span className="truncate text-xs text-muted-foreground">{chosen ? `Selected: ${chosen.name}` : ' '}</span>
          <span className="flex gap-2">
            {replacing && (
              <Button variant="ghost" onClick={onCancel}>
                Back
              </Button>
            )}
            <Button onClick={submit} disabled={!selected || choose.isPending || confirming}>
              Use this folder
            </Button>
          </span>
        </div>
      </CardContent>
    </Card>
  )
}

function FirstSync({ onChange }: { onChange: () => void }) {
  const folder = useQuery({
    ...folderQuery(),
    meta: { handles401: true },
    refetchInterval: (q) => {
      const d = q.state.data
      return d && d.last_synced_at !== null && syncProgress(d.counts_by_status).pending === 0 ? false : POLL_MS
    },
  })
  const data = folder.data
  if (folder.isError) {
    return (
      <Alert variant="destructive" className="max-w-xl">
        <AlertDescription>Could not read the sync status. Reload to try again.</AlertDescription>
      </Alert>
    )
  }
  if (!data) return <p className="text-sm text-muted-foreground">Loading…</p>
  const { processed, pending, total } = syncProgress(data.counts_by_status)
  const finished = data.last_synced_at !== null && pending === 0
  return (
    <Card className="w-full max-w-xl">
      <CardHeader>
        <CardTitle className="text-xl">{finished ? 'First sync complete' : 'Reading your documents'}</CardTitle>
        <CardDescription>{data.name}</CardDescription>
      </CardHeader>
      <CardContent>
        <Progress value={processed} max={Math.max(total, 1)} aria-label="Files processed" />
        <p className="text-sm font-medium">
          {processed} of {total} processed
        </p>
        {data.last_error && (
          <Alert variant="destructive">
            <AlertDescription>{data.last_error}</AlertDescription>
          </Alert>
        )}
        <p className="text-sm text-muted-foreground">
          {finished
            ? 'Everything in the folder has been read.'
            : 'You can open the Library now. Documents become searchable as each one finishes.'}
        </p>
        <div className="flex items-center justify-between gap-3">
          <Button variant="ghost" onClick={onChange}>
            Change folder
          </Button>
          <Button asChild>
            <Link to="/library">Open Library</Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

function SignedIn({ me }: { me: Me }) {
  const qc = useQueryClient()
  const [phase, setPhase] = useState<'choose' | 'sync'>(me.has_folder ? 'sync' : 'choose')
  const [hadFolder, setHadFolder] = useState(false)
  const replacing = me.has_folder || hadFolder
  const currentName = qc.getQueryData<FolderStatus>(keys.folder)?.name

  if (phase === 'choose') {
    return (
      <FolderChooser
        replacing={replacing}
        currentName={currentName}
        onCancel={() => setPhase('sync')}
        onChosen={(status) => {
          // The old folder's data is gone server-side; drop every cached view of it.
          qc.removeQueries({ predicate: (q) => q.queryKey[0] !== 'folders' && q.queryKey[0] !== 'connect-me' })
          qc.setQueryData(keys.folder, status)
          qc.setQueryData<Me>(['connect-me'], (m) => (m ? { ...m, has_folder: true } : m))
          setHadFolder(true)
          setPhase('sync')
        }}
      />
    )
  }
  return <FirstSync onChange={() => setPhase('choose')} />
}

export function Connect() {
  const [params] = useSearchParams()
  const me = useQuery({
    queryKey: ['connect-me'],
    queryFn: api.me,
    retry: false,
    // A 401 here means "signed out", not "session expired"; keep ?error= in the URL.
    meta: { handles401: true },
  })
  const signedOut = me.error instanceof ApiError && me.error.status === 401
  return (
    <Shell>
      {me.isPending && <p className="text-sm text-muted-foreground">Loading…</p>}
      {signedOut && <SignedOut error={params.get('error')} />}
      {me.isError && !signedOut && (
        <Alert variant="destructive" className="max-w-sm">
          <AlertDescription>Could not reach the server.</AlertDescription>
        </Alert>
      )}
      {me.data && <SignedIn me={me.data} />}
    </Shell>
  )
}
