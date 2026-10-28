import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { FolderStatus } from '@/lib/api'
import { SyncPill, syncState } from './SyncPill'

const base: FolderStatus = {
  drive_folder_id: 'fold1',
  name: 'f',
  last_synced_at: null,
  last_error: null,
  counts_by_status: { done: 3 },
  needs_reconnect: false,
}

describe('syncState', () => {
  it('is synced when nothing is pending', () => {
    expect(syncState(base).kind).toBe('synced')
  })
  it('is syncing with progress when files are queued or processing', () => {
    expect(syncState({ ...base, counts_by_status: { done: 5, queued: 6, processing: 3 } })).toEqual({
      kind: 'syncing',
      done: 5,
      total: 14,
    })
  })
  it('is stopped on needs_reconnect or a last_error, and that wins over pending', () => {
    expect(syncState({ ...base, needs_reconnect: true, counts_by_status: { queued: 1 } }).kind).toBe('stopped')
    expect(syncState({ ...base, last_error: 'boom' }).kind).toBe('stopped')
  })
})

describe('SyncPill', () => {
  it.each([
    [base, 'Synced'],
    [{ ...base, counts_by_status: { done: 1, queued: 1 } }, 'Syncing · 1 of 2'],
    [{ ...base, needs_reconnect: true }, 'Sync stopped'],
  ])('renders %#', (folder, text) => {
    render(<SyncPill folder={folder} />)
    expect(screen.getByRole('status')).toHaveTextContent(text)
  })
})
