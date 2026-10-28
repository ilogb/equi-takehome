import { CircleAlert, CircleCheck, CircleHelp, CircleSlash, Clock, Loader, ScanLine } from 'lucide-react'
import type { ComponentType } from 'react'
import { cn } from '@/lib/utils'

export const FILE_STATUSES = [
  'queued',
  'processing',
  'done',
  'needs_review',
  'failed',
  'unsupported',
  'scanned_no_text',
] as const
export type FileStatus = (typeof FILE_STATUSES)[number]

type Variant = 'muted' | 'primary' | 'success' | 'warning' | 'destructive' | 'dashed' | 'secondary'

const CONFIG: Record<FileStatus, { label: string; variant: Variant; icon: ComponentType<{ className?: string }> }> = {
  queued: { label: 'Queued', variant: 'muted', icon: Clock },
  processing: { label: 'Processing', variant: 'primary', icon: Loader },
  done: { label: 'Done', variant: 'success', icon: CircleCheck },
  needs_review: { label: 'Needs review', variant: 'warning', icon: CircleHelp },
  failed: { label: 'Failed', variant: 'destructive', icon: CircleAlert },
  unsupported: { label: 'Unsupported', variant: 'dashed', icon: CircleSlash },
  scanned_no_text: { label: 'Scanned: no text', variant: 'secondary', icon: ScanLine },
}

const VARIANT_CLASS: Record<Variant, string> = {
  muted: 'text-muted-foreground',
  primary: 'border-primary/40 bg-primary/10 text-primary',
  success: 'border-success/40 text-success',
  warning: 'border-warning/40 bg-warning-soft text-warning',
  destructive: 'border-transparent bg-destructive text-destructive-foreground',
  dashed: 'border-dashed text-muted-foreground',
  secondary: 'border-transparent bg-secondary text-secondary-foreground',
}

export function StatusBadge({ status, className }: { status: FileStatus; className?: string }) {
  const { label, variant, icon: Icon } = CONFIG[status]
  return (
    <span
      data-variant={variant}
      className={cn(
        'inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-xs font-semibold',
        VARIANT_CLASS[variant],
        className,
      )}
    >
      <Icon className={cn('size-3', status === 'processing' && 'animate-spin')} aria-hidden />
      {label}
    </span>
  )
}
