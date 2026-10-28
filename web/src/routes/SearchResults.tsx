import { useQuery } from '@tanstack/react-query'
import { SearchX, Tag } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Skeleton } from '@/components/ui/skeleton'
import { api, fundName, keys, useAnalyzeAnswer, useFindSearch, type AnalyzeResponse, type SearchHit } from '@/lib/api'
import { cn } from '@/lib/utils'

const NUMERIC = /^[+\-−(]?[$£€]?\d[\d,]*(\.\d+)?\s?(%|[kKmMbB]n?)?\)?$/

function escapeRe(s: string) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/** Wraps query terms in <mark>. Pure React nodes, so the text is always escaped. */
function Highlight({ text, query }: { text: string; query: string }): ReactNode {
  const terms = query.split(/\s+/).filter((t) => t.length > 1)
  if (terms.length === 0) return text
  const re = new RegExp(`(${terms.map(escapeRe).join('|')})`, 'gi')
  return text.split(re).map((part, i) =>
    i % 2 === 1 ? (
      <mark key={i} className="rounded-sm bg-primary/20 px-0.5 text-foreground">
        {part}
      </mark>
    ) : (
      part
    ),
  )
}


function HitMeta({ hit }: { hit: SearchHit }) {
  const parts = [hit.doc_type, hit.manager, hit.as_of_date ? `as of ${hit.as_of_date}` : null].filter(Boolean)
  return <p className="text-xs text-muted-foreground">{parts.join(' · ')}</p>
}

function Tags({ tags }: { tags: string[] }) {
  if (tags.length === 0) return null
  return (
    <ul className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
      {tags.map((t) => (
        <li key={t} className="inline-flex items-center gap-1">
          <Tag aria-hidden className="size-3" />
          {t}
        </li>
      ))}
    </ul>
  )
}

/** Same fund first, then same manager, then the rest in score order. */
function rankSimilar(selected: SearchHit, hits: SearchHit[]): SearchHit[] {
  const funds = new Set(selected.funds.map(fundName))
  const rank = (h: SearchHit) =>
    h.funds.some((f) => funds.has(fundName(f))) ? 0 : h.manager && h.manager === selected.manager ? 1 : 2
  return hits
    .filter((h) => h.document_id !== selected.document_id)
    .map((h, i) => ({ h, i }))
    .sort((a, b) => rank(a.h) - rank(b.h) || a.i - b.i)
    .map((x) => x.h)
}

function similarQuery(h: SearchHit) {
  return [h.funds[0] ? fundName(h.funds[0]) : h.manager, h.doc_type].filter(Boolean).join(' ')
}

/** First hit reuses similar_for_first; any other hit runs one search on its fund/manager. */
function SimilarPanel({ selected, isFirst, firstSimilar }: { selected: SearchHit; isFirst: boolean; firstSimilar: SearchHit[] }) {
  const q = similarQuery(selected)
  const other = useQuery({
    queryKey: keys.search(`similar:${selected.document_id}:${q}`),
    queryFn: () => api.search(q, 8),
    enabled: !isFirst && q !== '',
    retry: false,
  })
  const items = isFirst ? firstSimilar : rankSimilar(selected, other.data?.hits ?? [])
  const loading = !isFirst && other.isPending && q !== ''
  return (
    <aside aria-label="Similar documents" className="space-y-3 rounded-lg border bg-card p-4">
      <h2 className="text-sm font-semibold">Similar to {selected.file_name}</h2>
      {loading ? (
        <Skeleton className="h-16 w-full" />
      ) : items.length === 0 ? (
        <p className="text-sm text-muted-foreground">No similar documents.</p>
      ) : (
        <ul className="space-y-3">
          {items.map((h) => (
            <li key={h.document_id}>
              <Link to={`/documents/${h.document_id}`} className="text-sm font-medium hover:underline">
                {h.file_name}
              </Link>
              <HitMeta hit={h} />
            </li>
          ))}
        </ul>
      )}
    </aside>
  )
}

function Find({ q }: { q: string }) {
  const search = useFindSearch(q)
  const [selectedId, setSelectedId] = useState<number | null>(null)

  if (search.isPending) return <Skeleton className="h-40 w-full" />
  if (search.isError) return <p role="alert" className="text-sm text-negative">Search failed. Try again.</p>
  const { hits, similar_for_first } = search.data
  if (hits.length === 0)
    return (
      <div className="flex flex-col items-center gap-2 py-16 text-center">
        <SearchX aria-hidden className="size-8 text-muted-foreground" />
        <p className="font-medium">No documents match “{q}”</p>
        <p className="text-sm text-muted-foreground">Try fewer words, a fund name, or switch to Analyze to ask a question.</p>
      </div>
    )
  const selected = hits.find((h) => h.document_id === selectedId) ?? hits[0]
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
      <ul className="space-y-3">
        {hits.map((h) => (
          <li
            key={h.document_id}
            className={cn('rounded-lg border bg-card p-4', h.document_id === selected.document_id && 'ring-2 ring-primary/40')}
          >
            <div className="flex items-start justify-between gap-3">
              <Link to={`/documents/${h.document_id}`} className="font-medium hover:underline">
                {h.file_name}
              </Link>
              <button
                type="button"
                aria-label={`Select ${h.file_name}`}
                aria-pressed={h.document_id === selected.document_id}
                onClick={() => setSelectedId(h.document_id)}
                className="shrink-0 text-xs text-muted-foreground hover:text-foreground"
              >
                Show similar
              </button>
            </div>
            <p className="text-xs text-muted-foreground">{h.path}</p>
            <HitMeta hit={h} />
            <p className="mt-2 text-sm">
              <Highlight text={h.snippet} query={q} />
            </p>
            <div className="mt-2">
              <Tags tags={h.tags} />
            </div>
          </li>
        ))}
      </ul>
      <SimilarPanel
        selected={selected}
        isFirst={selected.document_id === hits[0].document_id}
        firstSimilar={similar_for_first}
      />
    </div>
  )
}

function AnswerTable({ table }: { table: NonNullable<AnalyzeResponse['table']> }) {
  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full text-sm">
        <thead className="bg-muted/50">
          <tr>
            {table.columns.map((c, i) => (
              <th key={i} scope="col" className="px-3 py-2 text-left font-medium">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((r, i) => (
            <tr key={i} className="border-t">
              {r.map((cell, j) => (
                <td key={j} className={cn('px-3 py-2', NUMERIC.test(cell.trim()) && 'text-right tabular-nums')}>
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

function Analyze({ q }: { q: string }) {
  const answer = useAnalyzeAnswer(q)
  if (answer.isPending)
    return (
      <div className="space-y-3" role="status">
        <p className="text-sm text-muted-foreground">Looking up your data (up to 5 lookups)</p>
        <Skeleton className="h-5 w-2/3" />
        <Skeleton className="h-24 w-full" />
      </div>
    )
  if (answer.isError) return <p role="alert" className="text-sm text-negative">Couldn't answer right now — try again.</p>
  const { text, table, sources, steps } = answer.data
  return (
    <div className="space-y-5">
      <p className="whitespace-pre-wrap text-base">{text}</p>
      {table && <AnswerTable table={table} />}
      {sources.length > 0 && (
        <div>
          <h2 className="mb-2 text-sm font-semibold">Sources</h2>
          <ul className="flex flex-wrap gap-2">
            {sources.map((s) => (
              <li key={s.document_id}>
                <Link
                  to={`/documents/${s.document_id}`}
                  className="inline-block rounded-full border px-3 py-1 text-xs hover:bg-muted"
                >
                  {s.file_name}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
      {steps.length > 0 && (
        <div>
          <h2 className="mb-2 text-sm font-semibold">Steps</h2>
          <ol className="list-decimal space-y-1 pl-5 text-sm text-muted-foreground">
            {steps.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ol>
        </div>
      )}
    </div>
  )
}

/** /search?q=&mode=find|analyze — one page for both modes of the header search box. */
export function SearchResults() {
  const [params] = useSearchParams()
  const q = (params.get('q') ?? '').trim()
  const mode = params.get('mode') === 'analyze' ? 'analyze' : 'find'
  return (
    <section className="mx-auto max-w-[1480px] space-y-4 px-4 py-6">
      <h1 className="text-lg font-semibold tracking-tight">
        {mode === 'analyze' ? 'Analyze' : 'Find'}
        {q && <span className="font-normal text-muted-foreground">: {q}</span>}
      </h1>
      {q === '' ? (
        <p className="text-sm text-muted-foreground">Type in the search box above.</p>
      ) : mode === 'analyze' ? (
        <Analyze key={q} q={q} />
      ) : (
        <Find key={q} q={q} />
      )}
    </section>
  )
}
