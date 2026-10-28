/** PDF pane, loaded lazily so react-pdf and pdf.js stay out of the main bundle. */
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Document, Page, pdfjs } from 'react-pdf'
import 'react-pdf/dist/Page/TextLayer.css'
import { Button } from '@/components/ui/button'
import { ApiError } from '@/lib/api'
import { useContent } from '@/lib/fileContent'

// Vite serves the worker as its own asset; the URL must be resolved from this module.
pdfjs.GlobalWorkerOptions.workerSrc = new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url).toString()

function Note({ children }: { children: React.ReactNode }) {
  return <p className="p-6 text-sm text-muted-foreground">{children}</p>
}

export default function PdfPane({ fileId, onMissing }: { fileId: number; onMissing: () => void }) {
  const content = useContent(fileId, 'buffer', true)
  const [pages, setPages] = useState(0)
  const [page, setPage] = useState(1)
  const [width, setWidth] = useState(560)
  const box = useRef<HTMLDivElement>(null)
  // pdf.js takes ownership of the bytes it is given, so hand it a copy.
  const file = useMemo(() => (content.data instanceof ArrayBuffer ? { data: content.data.slice(0) } : null), [content.data])

  useEffect(() => {
    if (content.error instanceof ApiError && content.error.status === 404) onMissing()
  }, [content.error, onMissing])

  useEffect(() => {
    const el = box.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(280, Math.floor(e.contentRect.width) - 16)))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  if (content.isError) return <Note>Could not load the file.</Note>
  if (!file) return <Note>Loading…</Note>
  return (
    <div ref={box} className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center justify-between border-b px-3 py-1.5 text-xs text-muted-foreground">
        <div className="flex items-center gap-1">
          <Button size="icon" variant="ghost" className="size-6" aria-label="Previous page" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            <ChevronLeft aria-hidden />
          </Button>
          <span>{pages > 0 ? `Page ${page} of ${pages}` : 'Loading…'}</span>
          <Button size="icon" variant="ghost" className="size-6" aria-label="Next page" disabled={page >= pages} onClick={() => setPage(page + 1)}>
            <ChevronRight aria-hidden />
          </Button>
        </div>
        <span>Streamed from Google Drive</span>
      </div>
      <div className="min-h-0 flex-1 overflow-auto bg-muted/40 p-2">
        <Document
          file={file}
          onLoadSuccess={({ numPages }) => setPages(numPages)}
          loading={<Note>Loading…</Note>}
          error={<Note>This PDF could not be displayed.</Note>}
        >
          <Page pageNumber={page} width={width} renderAnnotationLayer={false} />
        </Document>
      </div>
    </div>
  )
}

