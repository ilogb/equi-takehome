import { CloudOff, RefreshCw, Check } from 'lucide-react'
import type { FolderStatus } from '@/lib/api'
import { cn } from '@/lib/utils'

export type SyncState =
  | { kind: 'synced'; lastSyncedAt: string | null }
  | { kind: 'syncing'; done: number; total: number }
  | { kind: 'stopped'; reason: string }

/** Pure mapping from the folder status payload to what the pill shows. */
export function syncState(folder: FolderStatus): SyncState {
  if (folder.needs_reconnect) return { kind: 'stopped', reason: 'Google needs to be reconnected' }
  if (folder.last_error) return { kind: 'stopped', reason: folder.last_error }
  const c = folder.counts_by_status
  const pending = (c.queued ?? 0) + (c.processing ?? 0)
  if (pending > 0) {
    const total = Object.values(c).reduce((a, b) => a + (b ?? 0), 0)
    return { kind: 'syncing', done: total - pending, total }
  }
  return { kind: 'synced', lastSyncedAt: folder.last_synced_at }
}

export function relativeTime(iso: string | null, now = Date.now()): string {
  if (!iso) return ''
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000))
  if (s < 60) return `${s} s ago`
  if (s < 3600) return `${Math.floor(s / 60)} min ago`
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`
  return `${Math.floor(s / 86400)} d ago`
}

export function SyncPill({ folder, className }: { folder: FolderStatus; className?: string }) {
  const state = syncState(folder)
  const base = 'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium'
  if (state.kind === 'stopped') {
    return (
      <span
        role="status"
        title={state.reason}
        className={cn(base, 'border-destructive/40 bg-destructive/10 text-negative', className)}
      >
        <CloudOff className="size-3" aria-hidden />
        Sync stopped
      </span>
    )
  }
  if (state.kind === 'syncing') {
    return (
      <span role="status" className={cn(base, 'border-primary/40 bg-primary/10 text-primary', className)}>
        <RefreshCw className="size-3 animate-spin" aria-hidden />
        Syncing · {state.done} of {state.total}
      </span>
    )
  }
  const ago = relativeTime(state.lastSyncedAt)
  return (
    <span role="status" className={cn(base, 'text-muted-foreground', className)}>
      <Check className="size-3 text-success" aria-hidden />
      {ago ? `Synced ${ago}` : 'Synced'}
    </span>
  )
}
