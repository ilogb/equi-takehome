import { cn } from '@/lib/utils'

const BASE =
  'inline-flex size-4 items-center justify-center rounded-sm border text-[11px] font-semibold leading-none'

/** "?" next to a value the extractor flagged as uncertain. */
export function ReviewMarker({ reason, className }: { reason?: string | null; className?: string }) {
  const title = reason ? `Needs review: ${reason}` : 'Needs review'
  return (
    <span
      role="img"
      aria-label={title}
      title={title}
      className={cn(BASE, 'border-warning/50 bg-warning-soft text-warning', className)}
    >
      ?
    </span>
  )
}

/** "≠" next to a value that two current documents report differently. */
export function DiffMarker({ detail, className }: { detail?: string | null; className?: string }) {
  const title = detail ? `Sources differ: ${detail}` : 'Sources differ'
  return (
    <span
      role="img"
      aria-label={title}
      title={title}
      className={cn(BASE, 'border-diff/50 bg-diff-soft text-diff', className)}
    >
      {'≠'}
    </span>
  )
}
