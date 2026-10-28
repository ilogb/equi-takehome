import { File, FileImage, FileSpreadsheet, FileText, Globe, type LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'

export type FileKind = 'pdf' | 'csv' | 'spreadsheet' | 'html' | 'text' | 'image' | 'other'

const ICONS: Record<FileKind, { icon: LucideIcon; color: string; label: string }> = {
  pdf: { icon: FileText, color: 'text-[hsl(var(--ft-pdf))]', label: 'PDF' },
  csv: { icon: FileSpreadsheet, color: 'text-[hsl(var(--ft-sheet))]', label: 'CSV' },
  spreadsheet: { icon: FileSpreadsheet, color: 'text-[hsl(var(--ft-sheet))]', label: 'Spreadsheet' },
  html: { icon: Globe, color: 'text-[hsl(var(--ft-mail))]', label: 'HTML' },
  text: { icon: FileText, color: 'text-muted-foreground', label: 'Text' },
  image: { icon: FileImage, color: 'text-muted-foreground', label: 'Image' },
  other: { icon: File, color: 'text-muted-foreground', label: 'File' },
}

export function FileTypeIcon({ kind, className }: { kind: FileKind; className?: string }) {
  const { icon: Icon, color, label } = ICONS[kind]
  return <Icon className={cn('size-4 shrink-0', color, className)} role="img" aria-label={label} />
}
