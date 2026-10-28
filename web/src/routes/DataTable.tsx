/** /data: one row per number across every fund and account, filtered, sorted and paged on the server (T1-T3). */
import { useQuery } from '@tanstack/react-query'
import { flexRender, getCoreRowModel, useReactTable, type ColumnDef } from '@tanstack/react-table'
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronDown, Download } from 'lucide-react'
import { useMemo, useState, type ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { DiffMarker, ReviewMarker } from '@/components/Markers'
import { Button } from '@/components/ui/button'
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { api, keys, urls, type DataRow, type Measure, type PeriodKind, type RowsFilters } from '@/lib/api'
import { formatMoney, formatPercent } from '@/lib/format'
import { cn } from '@/lib/utils'

const DEFAULT_LIMIT = 100
const MAX_LIMIT = 500
const FUND_MEASURES: Measure[] = ['return', 'benchmark_return', 'aum', 'nav']
const ACCOUNT_MEASURES: Measure[] = ['account_value', 'account_return']
const MEASURES: Measure[] = [...FUND_MEASURES, ...ACCOUNT_MEASURES]
const PERCENT_MEASURES = new Set<Measure>(['return', 'benchmark_return', 'account_return'])
const PERIOD_KINDS: PeriodKind[] = ['month', 'qtd', 'ytd', '1y', '3y', '5y', 'itd', 'other']
const MEASURE_LABEL: Record<Measure, string> = {
  return: 'Return',
  benchmark_return: 'Benchmark return',
  aum: 'AUM',
  nav: 'NAV',
  account_value: 'Account value',
  account_return: 'Account return',
}
const SORTS = ['value', 'period_end', 'entity'] as const
type Sort = (typeof SORTS)[number]
const FILTER_KEYS = ['fund', 'manager', 'measure', 'period_kind', 'start', 'end', 'needs_review', 'conflict'] as const

const isDate = (v: string | null): v is string => v != null && /^\d{4}-\d{2}-\d{2}$/.test(v)

/** Everything the table shows is derived from the URL; unknown or malformed values are dropped. */
function parseFilters(p: URLSearchParams): Required<Pick<RowsFilters, 'sort' | 'order' | 'limit' | 'offset'>> & RowsFilters {
  const measure = MEASURES.find((m) => m === p.get('measure'))
  const period_kind = PERIOD_KINDS.find((k) => k === p.get('period_kind'))
  const sort = SORTS.find((s) => s === p.get('sort')) ?? 'period_end'
  const limit = Number(p.get('limit'))
  const offset = Number(p.get('offset'))
  const start = p.get('start')
  const end = p.get('end')
  return {
    fund: p.get('fund') || undefined,
    manager: p.get('manager') || undefined,
    measure,
    period_kind,
    start: isDate(start) ? start : undefined,
    end: isDate(end) ? end : undefined,
    needs_review: p.get('needs_review') === 'true' ? true : undefined,
    conflict: p.get('conflict') === 'true' ? true : undefined,
    sort,
    order: p.get('order') === 'asc' ? 'asc' : 'desc',
    limit: Number.isInteger(limit) && limit >= 1 ? Math.min(limit, MAX_LIMIT) : DEFAULT_LIMIT,
    offset: Number.isInteger(offset) && offset > 0 ? offset : 0,
  }
}

interface Option {
  value: string
  label: string
}

/** Popover + Command single-select; picking the selected option again clears it. */
function FacetFilter({
  label,
  value,
  display,
  groups,
  onChange,
}: {
  label: string
  value: string | undefined
  display: string | undefined
  groups: { heading?: string; options: Option[] }[]
  onChange: (v: string | undefined) => void
}) {
  const [open, setOpen] = useState(false)
  const pick = (v: string) => {
    onChange(v === value ? undefined : v)
    setOpen(false)
  }
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className={cn('h-8 gap-1.5', value && 'border-primary/50')}>
          {label}
          {display && <span className="font-semibold">{display}</span>}
          <ChevronDown className="size-3.5 opacity-60" aria-hidden />
        </Button>
      </PopoverTrigger>
      <PopoverContent>
        <Command>
          <CommandInput placeholder={`Filter ${label.toLowerCase()}`} aria-label={`Filter ${label.toLowerCase()}`} />
          <CommandList>
            <CommandEmpty>No matches.</CommandEmpty>
            {groups.map((g, i) => (
              <CommandGroup key={g.heading ?? i} heading={g.heading}>
                {g.options.map((o) => (
                  <CommandItem key={o.value} value={`${o.label} ${o.value}`} onSelect={() => pick(o.value)}>
                    {o.label}
                  </CommandItem>
                ))}
              </CommandGroup>
            ))}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}

function Toggle({ label, checked, onChange }: { label: ReactNode; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={cn(
        'inline-flex h-8 items-center gap-1.5 rounded-md border px-2.5 text-sm transition-colors hover:bg-muted',
        checked && 'border-primary/50 bg-secondary font-medium',
      )}
    >
      {label}
    </button>
  )
}

function formatValue(r: DataRow): string {
  return PERCENT_MEASURES.has(r.measure) ? formatPercent(r.value) : formatMoney(r.value, r.currency)
}

const identity = (r: DataRow) => [r.entity, r.share_class, r.measure, r.period_kind, r.period_end].join('|')

/** "month 2026-01-31: 2.37% in a.csv, 2.35% in b.pdf" from the rows on this page that share the identity. */
function conflictDetail(r: DataRow, all: DataRow[]): string {
  const peers = all.filter((o) => o.conflict && identity(o) === identity(r))
  return `${r.period_kind} ${r.period_end}: ${peers.map((o) => `${formatValue(o)} in ${o.document_name}`).join(', ')}`
}

function SortHeader({
  label,
  active,
  order,
  onClick,
}: {
  label: string
  active: boolean
  order: 'asc' | 'desc'
  onClick: () => void
}) {
  const Icon = !active ? ArrowUpDown : order === 'asc' ? ArrowUp : ArrowDown
  return (
    <button
      type="button"
      aria-label={`Sort by ${label.toLowerCase()}`}
      onClick={onClick}
      className="-mx-1 inline-flex items-center gap-1 rounded px-1 hover:text-foreground"
    >
      {label}
      <Icon className={cn('size-3', !active && 'opacity-50')} aria-hidden />
    </button>
  )
}

export function DataTable() {
  const [params, setParams] = useSearchParams()
  const f = parseFilters(params)
  const patch = (changes: Record<string, string | undefined>, keepOffset = false) =>
    setParams((p) => {
      const n = new URLSearchParams(p)
      for (const [k, v] of Object.entries(changes)) {
        if (v === undefined || v === '') n.delete(k)
        else n.set(k, v)
      }
      if (!keepOffset) n.delete('offset')
      return n
    })
  const clearAll = () => setParams(new URLSearchParams())

  const funds = useQuery({ queryKey: keys.funds, queryFn: api.funds })
  const meta = useQuery({ queryKey: keys.meta, queryFn: api.meta })
  const rows = useQuery({ queryKey: keys.rows(f), queryFn: () => api.rows(f), placeholderData: (prev) => prev })

  const data = rows.data?.rows ?? []
  const total = rows.data?.total ?? 0
  const anyFilter = FILTER_KEYS.some((k) => f[k] !== undefined)

  const setSort = (s: Sort) =>
    patch({
      sort: s,
      order: f.sort === s ? (f.order === 'desc' ? 'asc' : 'desc') : s === 'entity' ? 'asc' : 'desc',
    })

  const columns = useMemo<ColumnDef<DataRow>[]>(() => {
    const sortable = (id: Sort, label: string) => ({
      id,
      header: () => <SortHeader label={label} active={f.sort === id} order={f.order} onClick={() => setSort(id)} />,
    })
    return [
      {
        ...sortable('entity', 'Fund or account'),
        cell: ({ row: { original: r } }) => <span className="font-medium">{r.entity}</span>,
      },
      { id: 'share_class', header: 'Share class', cell: ({ row: { original: r } }) => r.share_class ?? '—' },
      {
        ...sortable('period_end', 'Period'),
        cell: ({ row: { original: r } }) => <span className="tabular-nums">{`${r.period_kind} · ${r.period_end}`}</span>,
      },
      { id: 'measure', header: 'Measure', cell: ({ row: { original: r } }) => MEASURE_LABEL[r.measure] },
      {
        ...sortable('value', 'Value'),
        cell: ({ row: { original: r } }) => (
          <span className={cn('tabular-nums', r.value.startsWith('-') && 'text-negative')}>{formatValue(r)}</span>
        ),
      },
      {
        id: 'markers',
        header: 'Markers',
        cell: ({ row: { original: r } }) => (
          <span className="inline-flex gap-1">
            {r.needs_review && <ReviewMarker reason={r.review_reason} />}
            {r.conflict && <DiffMarker detail={conflictDetail(r, data)} />}
          </span>
        ),
      },
      {
        id: 'source',
        header: 'Source',
        cell: ({ row: { original: r } }) => (
          <Link to={`/documents/${r.document_id}`} className="block max-w-56 truncate text-primary hover:underline" title={r.document_name}>
            {r.document_name}
          </Link>
        ),
      },
    ]
    // eslint-disable-next-line react-hooks/exhaustive-deps -- setSort only reads f.sort/f.order, already listed
  }, [f.sort, f.order, data])

  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
    manualSorting: true,
    manualFiltering: true,
    manualPagination: true,
    getRowId: (r) => String(r.id),
  })

  const fundName = funds.data?.find((x) => String(x.id) === f.fund)?.name ?? f.fund
  const from = data.length === 0 ? 0 : f.offset + 1
  const to = f.offset + data.length
  const csv = urls.rowsCsv({ ...f, limit: undefined, offset: undefined })

  return (
    <section className="mx-auto max-w-[1480px] space-y-4 px-4 py-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Data</h1>
          <p className="text-sm text-muted-foreground">
            Common rows across every fund and account
            {rows.data ? ` · ${total.toLocaleString('en-US')} ${total === 1 ? 'row' : 'rows'}` : ''}
          </p>
        </div>
        <Button asChild size="sm" variant="outline">
          <a href={csv} download>
            <Download aria-hidden />
            Export CSV
          </a>
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Filters">
        <FacetFilter
          label="Fund or account"
          value={f.fund}
          display={fundName}
          groups={[{ options: (funds.data ?? []).map((x) => ({ value: String(x.id), label: x.name })) }]}
          onChange={(v) => patch({ fund: v })}
        />
        <FacetFilter
          label="Manager"
          value={f.manager}
          display={f.manager}
          groups={[{ options: (meta.data?.managers ?? []).map((m) => ({ value: m, label: m })) }]}
          onChange={(v) => patch({ manager: v })}
        />
        <FacetFilter
          label="Measure"
          value={f.measure}
          display={f.measure && MEASURE_LABEL[f.measure]}
          groups={[
            { heading: 'Fund measures', options: FUND_MEASURES.map((m) => ({ value: m, label: MEASURE_LABEL[m] })) },
            {
              heading: 'Account measures · from statements',
              options: ACCOUNT_MEASURES.map((m) => ({ value: m, label: MEASURE_LABEL[m] })),
            },
          ]}
          onChange={(v) => patch({ measure: v })}
        />
        <FacetFilter
          label="Period kind"
          value={f.period_kind}
          display={f.period_kind}
          groups={[{ options: (meta.data?.period_kinds ?? PERIOD_KINDS).map((k) => ({ value: k, label: k })) }]}
          onChange={(v) => patch({ period_kind: v })}
        />
        <label className="flex items-center gap-1.5 text-sm text-muted-foreground">
          From
          <Input
            type="date"
            className="h-8 w-36"
            value={f.start ?? ''}
            min={meta.data?.min_period_end ?? undefined}
            onChange={(e) => patch({ start: e.target.value })}
          />
        </label>
        <label className="flex items-center gap-1.5 text-sm text-muted-foreground">
          To
          <Input
            type="date"
            className="h-8 w-36"
            value={f.end ?? ''}
            max={meta.data?.max_period_end ?? undefined}
            onChange={(e) => patch({ end: e.target.value })}
          />
        </label>
        <Toggle
          label={<><span aria-hidden><ReviewMarker /></span> needs review</>}
          checked={f.needs_review === true}
          onChange={(v) => patch({ needs_review: v ? 'true' : undefined })}
        />
        <Toggle
          label={<><span aria-hidden><DiffMarker /></span> sources differ</>}
          checked={f.conflict === true}
          onChange={(v) => patch({ conflict: v ? 'true' : undefined })}
        />
      </div>

      {rows.isError && (
        <p role="alert" className="text-sm text-negative">
          Could not load rows. Try again in a moment.
        </p>
      )}

      <div className="overflow-x-auto rounded-xl border bg-background">
        <table className="w-full min-w-[900px] border-collapse text-sm">
          <thead>
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id} className="border-b text-left text-xs text-muted-foreground">
                {hg.headers.map((h) => (
                  <th
                    key={h.id}
                    scope="col"
                    aria-sort={
                      f.sort === h.column.id ? (f.order === 'asc' ? 'ascending' : 'descending') : undefined
                    }
                    className="px-3 py-2 font-medium"
                  >
                    {flexRender(h.column.columnDef.header, h.getContext())}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((r) => (
              <tr key={r.id} className="border-b hover:bg-muted/40">
                {r.getVisibleCells().map((c) => (
                  <td key={c.id} className="px-3 py-2">
                    {flexRender(c.column.columnDef.cell, c.getContext())}
                  </td>
                ))}
              </tr>
            ))}
            {rows.isSuccess && data.length === 0 && (
              <tr>
                <td colSpan={columns.length} className="px-3 py-10 text-center">
                  {anyFilter ? (
                    <div className="space-y-3">
                      <p className="text-muted-foreground">No rows match these filters.</p>
                      <Button size="sm" variant="outline" onClick={clearAll}>
                        Clear filters
                      </Button>
                    </div>
                  ) : (
                    <p className="text-muted-foreground">No extracted rows yet. Rows appear here as documents finish processing.</p>
                  )}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {total > 0 && (
        <div className="flex items-center justify-between gap-3 text-sm text-muted-foreground">
          <span className="tabular-nums">
            {from.toLocaleString('en-US')}–{to.toLocaleString('en-US')} of {total.toLocaleString('en-US')}
          </span>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={f.offset === 0}
              onClick={() => patch({ offset: String(Math.max(0, f.offset - f.limit)) }, true)}
            >
              Previous
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={to >= total}
              onClick={() => patch({ offset: String(f.offset + f.limit) }, true)}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </section>
  )
}
