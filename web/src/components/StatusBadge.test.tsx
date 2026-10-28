import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { FILE_STATUSES, StatusBadge, type FileStatus } from './StatusBadge'

const expected: Record<FileStatus, { text: string; variant: string }> = {
  queued: { text: 'Queued', variant: 'muted' },
  processing: { text: 'Processing', variant: 'primary' },
  done: { text: 'Done', variant: 'success' },
  needs_review: { text: 'Needs review', variant: 'warning' },
  failed: { text: 'Failed', variant: 'destructive' },
  unsupported: { text: 'Unsupported', variant: 'dashed' },
  scanned_no_text: { text: 'Scanned: no text', variant: 'secondary' },
}

describe('StatusBadge', () => {
  it('covers all seven backend statuses', () => {
    expect([...FILE_STATUSES].sort()).toEqual(Object.keys(expected).sort())
  })
  it.each(Object.entries(expected))('%s renders its label and variant', (status, { text, variant }) => {
    render(<StatusBadge status={status as FileStatus} />)
    const badge = screen.getByText(text)
    expect(badge).toBeInTheDocument()
    expect(badge.closest('[data-variant]')).toHaveAttribute('data-variant', variant)
  })
  it('renders a neutral fallback for an unknown status instead of throwing', () => {
    render(<StatusBadge status={'weird' as FileStatus} />)
    expect(screen.getByText('weird')).toHaveAttribute('data-variant', 'muted')
  })
})
