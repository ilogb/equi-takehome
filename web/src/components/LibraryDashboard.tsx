/** Summary above the Library: headline counts, latest 1-year return vs benchmark, latest AUM.
 *  Every number links to the rows behind it in Data (or the filtered Library list). */
import { useQuery } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { api, keys, type Dashboard } from '@/lib/api'
import { formatMoneyCompact, formatPercent } from '@/lib/format'
import { cn } from '@/lib/utils'

const count = (n: number) => n.toLocaleString('en-US')
const plural = (n: number, one: string, many = `${one}s`) => `${count(n)} ${n === 1 ? one : many}`

function Tile({ label, value, children }: { label: string; value: string; children?: ReactNode }) {
  return (
    <div role="group" aria-label={label} className="rounded-xl border bg-card p-4">
      <div className="text-sm text-muted-foreground">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums tracking-tight">{value}</div>
      <div className="mt-1 min-h-5 text-xs text-muted-foreground">{children}</div>
    </div>
  )
}

function TileLink({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link to={to} className="font-medium text-primary hover:underline">
      {children}
    </Link>
  )
}

function Swatch({ series }: { series: 'fund' | 'benchmark' }) {
  return (
    <span
      aria-hidden
      className={cn('inline-block size-2.5 shrink-0 rounded-[3px]', series === 'fund' ? 'bg-chart-fund' : 'bg-chart-benchmark')}
    />
  )
}

/** Horizontal bar from the zero line; 4px rounding only on the data end. */
function Bar({ value, scale, series }: { value: number; scale: (v: number) => number; series: 'fund' | 'benchmark' }) {
  const zero = scale(0)
  const end = scale(value)
  return (
    <div
      className={cn(
        'absolute h-2',
        series === 'fund' ? 'top-0 bg-chart-fund' : 'bottom-0 bg-chart-benchmark',
        value >= 0 ? 'rounded-r' : 'rounded-l',
      )}
      style={{ left: `${Math.min(zero, end)}%`, width: `${Math.max(Math.abs(end - zero), 0.5)}%` }}
    />
  )
}

function OneYearChart({ rows }: { rows: Dashboard['one_year'] }) {
  const values = rows.flatMap((r) => [Number(r.return), ...(r.benchmark == null ? [] : [Number(r.benchmark)])])
  const lo = Math.min(0, ...values)
  const hi = Math.max(0, ...values)
  const scale = (v: number) => ((v - lo) / (hi - lo || 1)) * 100
  return (
    <figure aria-label="1-year return vs benchmark" className="rounded-xl border bg-card p-4">
      <figcaption className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-sm font-semibold">1-year return vs benchmark</span>
        <span className="flex items-center gap-3 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <Swatch series="fund" />
            Fund
          </span>
          <span className="inline-flex items-center gap-1.5">
            <Swatch series="benchmark" />
            Benchmark
          </span>
        </span>
      </figcaption>
      <TooltipProvider>
        <ul className="mt-3 space-y-0.5">
          {rows.map((r) => {
            const ret = formatPercent(r.return)
            const bench = r.benchmark == null ? null : formatPercent(r.benchmark)
            return (
              <li key={r.entity}>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Link
                      to={`/data?${new URLSearchParams({ ...(r.fund_id != null && { fund: String(r.fund_id) }), measure: 'return', period_kind: '1y' })}`}
                      className="grid grid-cols-[minmax(0,13rem)_minmax(4rem,1fr)_6.5rem] items-center gap-3 rounded-md px-2 py-1.5 hover:bg-muted"
                    >
                      <span className="truncate text-sm">{r.entity}</span>
                      <span className="relative h-[18px]">
                        <span aria-hidden className="absolute inset-y-0 w-px bg-border" style={{ left: `${scale(0)}%` }} />
                        <Bar value={Number(r.return)} scale={scale} series="fund" />
                        {r.benchmark != null && <Bar value={Number(r.benchmark)} scale={scale} series="benchmark" />}
                      </span>
                      <span className="space-y-0.5 text-right text-xs tabular-nums">
                        <span className="flex items-center justify-end gap-1.5 font-medium">
                          <Swatch series="fund" />
                          {ret}
                        </span>
                        <span className="flex items-center justify-end gap-1.5 text-muted-foreground">
                          {bench == null ? (
                            'no benchmark'
                          ) : (
                            <>
                              <Swatch series="benchmark" />
                              {bench}
                            </>
                          )}
                        </span>
                      </span>
                    </Link>
                  </TooltipTrigger>
                  <TooltipContent side="top" sideOffset={4}>
                    {r.entity}: {ret} over the year to {r.period_end}
                    {bench != null && ` (benchmark ${bench})`}
                  </TooltipContent>
                </Tooltip>
              </li>
            )
          })}
        </ul>
      </TooltipProvider>
      <p className="mt-2 px-2 text-xs text-muted-foreground">Latest 1-year figure per fund. Click a fund for its rows in Data.</p>
    </figure>
  )
}

function AumList({ rows }: { rows: Dashboard['aum'] }) {
  return (
    <figure aria-label="Assets under management" className="rounded-xl border bg-card p-4">
      <figcaption className="text-sm font-semibold">Assets under management</figcaption>
      <ul className="mt-3 space-y-0.5">
        {rows.map((r) => (
          <li key={r.entity}>
            <Link
              to={`/data?${new URLSearchParams({ ...(r.fund_id != null && { fund: String(r.fund_id) }), measure: 'aum' })}`}
              className="flex items-baseline justify-between gap-3 rounded-md px-2 py-1.5 hover:bg-muted"
            >
              <span className="min-w-0">
                <span className="block truncate text-sm">{r.entity}</span>
                <span className="block text-xs text-muted-foreground">as of {r.period_end}</span>
              </span>
              <span className="shrink-0 text-sm font-medium tabular-nums">{formatMoneyCompact(r.value, r.currency)}</span>
            </Link>
          </li>
        ))}
      </ul>
      <p className="mt-2 px-2 text-xs text-muted-foreground">Each in its own currency, so not ranked against one scale.</p>
    </figure>
  )
}

export function LibraryDashboard() {
  const q = useQuery({ queryKey: keys.dashboard, queryFn: api.dashboard })
  if (!q.data) return null // the dashboard is a summary: a failure here must not block the Library
  const { documents, figures, entities, one_year, aum } = q.data
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Tile label="Documents" value={count(documents.total)}>
          {documents.needs_review > 0 && (
            <TileLink to="/library?status=needs_review">{documents.needs_review} need review</TileLink>
          )}
          {documents.needs_review > 0 && documents.failed > 0 && ' · '}
          {documents.failed > 0 && <TileLink to="/library?status=failed">{documents.failed} failed</TileLink>}
          {documents.processing > 0 && <span> · {documents.processing} processing</span>}
        </Tile>
        <Tile label="Funds tracked" value={count(entities.funds)}>
          {entities.accounts > 0 && `plus ${plural(entities.accounts, 'account')}`}
        </Tile>
        <Tile label="Data points" value={count(figures.total)}>
          {figures.needs_review > 0 && <TileLink to="/data?needs_review=true">{figures.needs_review} need review</TileLink>}
        </Tile>
        <Tile label="Sources differ" value={count(figures.conflicts)}>
          {figures.conflicts > 0 ? (
            <TileLink to="/data?conflict=true">Compare in Data</TileLink>
          ) : (
            'No disagreements between documents'
          )}
        </Tile>
      </div>
      {(one_year.length > 0 || aum.length > 0) && (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
          {one_year.length > 0 && <OneYearChart rows={one_year} />}
          {aum.length > 0 && <AumList rows={aum} />}
        </div>
      )}
    </div>
  )
}
