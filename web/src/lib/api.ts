/** Typed fetchers and TanStack Query hooks for every backend route. Decimals are canonical strings. */
import { queryOptions, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { FileKind } from '@/components/FileTypeIcon'
import type { FileStatus } from '@/components/StatusBadge'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    credentials: 'same-origin',
    ...init,
    headers: { ...(init?.body ? { 'Content-Type': 'application/json' } : {}), ...init?.headers },
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = (await res.json()) as { detail?: unknown }
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      /* non-JSON error body: keep statusText */
    }
    throw new ApiError(res.status, detail)
  }
  return (await res.json()) as T
}

function qs(params: object): string {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') sp.set(k, String(v))
  }
  const s = sp.toString()
  return s ? `?${s}` : ''
}

// ---- types ---------------------------------------------------------------------------------

export interface Me {
  email: string
  name: string | null
  needs_reconnect: boolean
  has_folder: boolean
}

export interface FolderStatus {
  name: string
  drive_folder_id: string
  last_synced_at: string | null
  last_error: string | null
  counts_by_status: Partial<Record<FileStatus, number>>
  needs_reconnect: boolean
}

export interface DriveFolder {
  id: string
  name: string
}

export interface FileRow {
  id: number
  document_id: number | null
  drive_file_id: string
  name: string
  path: string
  mime_type: string
  kind: FileKind
  status: FileStatus
  error: string | null
  missing_in_drive: boolean
  doc_type: string | null
  manager: string | null
  funds: HitFund[]
  as_of_date: string | null
  tags: string[]
  row_count: number
  updated_at: string
}

export type Measure = 'return' | 'benchmark_return' | 'aum' | 'nav' | 'account_value' | 'account_return'
export type PeriodKind = 'month' | 'qtd' | 'ytd' | '1y' | '3y' | '5y' | 'itd' | 'other'

export interface DataRow {
  id: number
  document_id: number
  document_name: string
  manager: string | null
  fund_id: number | null
  entity: string
  entity_kind: string
  share_class: string | null
  measure: Measure
  period_kind: PeriodKind
  period_end: string
  value: string
  value_as_written: string
  unit: string | null
  currency: string | null
  benchmark_name: string | null
  table_index: number | null
  row_index: number | null
  col_index: number | null
  needs_review: boolean
  review_reason: string | null
  conflict: boolean
}

export interface DocumentTable {
  index: number
  title: string | null
  /** One entry per printed header row. */
  header: string[][]
  /** The first 200 body rows; `rows_total` is the full count. */
  rows: string[][]
  rows_total: number
}

export interface DocumentFile {
  id: number
  status: FileStatus
  error: string | null
  missing_in_drive: boolean
  mime_type: string
  kind: FileKind
  path: string
  name: string
  drive_file_id: string
}

export interface DocumentDetail {
  id: number
  source_file_id: number
  name: string
  path: string
  mime_type: string
  status: FileStatus
  doc_type: string | null
  manager: string | null
  as_of_date: string | null
  currency: string | null
  summary: string | null
  tags: string[]
  funds: HitFund[]
  file: DocumentFile
  tables: DocumentTable[]
  /** At most 500 rows; `rows_total` is the full count (see /data?document_id=...). */
  rows: DataRow[]
  rows_total: number
}

export interface Fund {
  id: number
  name: string
  manager: string | null
  share_classes: string[]
  documents: number
}

export interface Meta {
  measures: Measure[]
  period_kinds: PeriodKind[]
  min_period_end: string | null
  max_period_end: string | null
  managers: string[]
}

export interface FilesFilters {
  status?: FileStatus
  q?: string
}

export interface RowsFilters {
  fund?: string
  manager?: string
  entity_kind?: string
  share_class?: string
  measure?: Measure
  period_kind?: PeriodKind
  start?: string
  end?: string
  needs_review?: boolean
  conflict?: boolean
  document_id?: number
  sort?: 'value' | 'period_end' | 'entity'
  order?: 'asc' | 'desc'
  limit?: number
  offset?: number
}

export interface RowsPage {
  rows: DataRow[]
  total: number
}

/** Mirrors backend/app/search/service.py SearchHit. Fund entries are {name, share_class} or a plain name. */
export type HitFund = string | { name: string; share_class?: string | null }

/** A fund entry's name, whichever shape it arrived in. */
export const fundName = (f: HitFund): string => (typeof f === 'string' ? f : f.name)

/** "Name (share class)" when a share class is known, else the name. */
export const fundLabel = (f: HitFund): string =>
  typeof f !== 'string' && f.share_class ? `${f.name} (${f.share_class})` : fundName(f)
export interface SearchHit {
  document_id: number
  file_name: string
  path: string
  doc_type: string
  manager: string | null
  funds: HitFund[]
  as_of_date: string | null
  tags: string[]
  snippet: string
  score: number
}
export interface SearchResponse {
  hits: SearchHit[]
  similar_for_first: SearchHit[]
}

/** Mirrors backend/app/analyze/loop.py. Table cells are already formatted strings. */
export interface AnalyzeTable {
  columns: string[]
  rows: string[][]
}
export interface AnalyzeResponse {
  text: string
  table: AnalyzeTable | null
  sources: { document_id: number; file_name: string }[]
  steps: string[]
}

// ---- fetchers ------------------------------------------------------------------------------

export const api = {
  me: () => request<Me>('/api/auth/me'),
  logout: () => request<{ ok: true }>('/api/auth/logout', { method: 'POST' }),
  folder: () => request<FolderStatus>('/api/folder'),
  searchFolders: (q: string) => request<DriveFolder[]>(`/api/folders${qs({ q })}`),
  chooseFolder: (folderId: string) =>
    request<FolderStatus>('/api/folder', { method: 'PUT', body: JSON.stringify({ folder_id: folderId }) }),
  syncNow: () => request<{ queued: number; ignored: number }>('/api/folder/sync', { method: 'POST' }),
  files: (f: FilesFilters = {}) => request<FileRow[]>(`/api/files${qs(f)}`),
  retryFile: (id: number) => request<{ id: number; status: FileStatus }>(`/api/files/${id}/retry`, { method: 'POST' }),
  reextractFile: (id: number) =>
    request<{ id: number; status: FileStatus }>(`/api/files/${id}/reextract`, { method: 'POST' }),
  document: (id: number) => request<DocumentDetail>(`/api/documents/${id}`),
  rows: (f: RowsFilters = {}) => request<RowsPage>(`/api/rows${qs(f)}`),
  funds: () => request<Fund[]>('/api/funds'),
  meta: () => request<Meta>('/api/meta'),
  search: (q: string, limit = 20) => request<SearchResponse>(`/api/search${qs({ q, limit })}`),
  analyze: (question: string) =>
    request<AnalyzeResponse>('/api/analyze', { method: 'POST', body: JSON.stringify({ question }) }),
}

/** URLs the browser opens directly rather than through fetch. */
export const urls = {
  fileContent: (id: number) => `/api/files/${id}/content`,
  rowsCsv: (f: RowsFilters = {}) => `/api/rows.csv${qs({ ...f, limit: undefined, offset: undefined })}`,
  googleStart: '/api/auth/google/start',
}

// ---- query keys and hooks ------------------------------------------------------------------

export const keys = {
  me: ['me'] as const,
  folder: ['folder'] as const,
  folders: (q: string) => ['folders', q] as const,
  files: (filters: FilesFilters) => ['files', filters] as const,
  document: (id: number) => ['document', id] as const,
  rows: (filters: RowsFilters) => ['rows', filters] as const,
  funds: ['funds'] as const,
  meta: ['meta'] as const,
  search: (q: string) => ['search', q] as const,
  analyze: (question: string) => ['analyze', question] as const,
}

export const meQuery = () => queryOptions({ queryKey: keys.me, queryFn: api.me, retry: false, staleTime: 60_000 })
export const folderQuery = () =>
  queryOptions({ queryKey: keys.folder, queryFn: api.folder, retry: false, refetchInterval: 10_000 })

export const useMe = () => useQuery(meQuery())
export const useFolder = () => useQuery(folderQuery())
export const useFiles = (filters: FilesFilters = {}) =>
  useQuery({ queryKey: keys.files(filters), queryFn: () => api.files(filters) })
export const useDocument = (id: number) =>
  useQuery({ queryKey: keys.document(id), queryFn: () => api.document(id), enabled: Number.isFinite(id) })
export const useRows = (filters: RowsFilters = {}) =>
  useQuery({ queryKey: keys.rows(filters), queryFn: () => api.rows(filters) })
export const useFunds = () => useQuery({ queryKey: keys.funds, queryFn: api.funds })
export const useMeta = () => useQuery({ queryKey: keys.meta, queryFn: api.meta })
export const useFindSearch = (q: string) =>
  useQuery({ queryKey: keys.search(q), queryFn: () => api.search(q), enabled: q.trim() !== '' })
/** One POST per question: the answer is cached for the session so Back never re-asks. */
export const useAnalyzeAnswer = (question: string) =>
  useQuery({
    queryKey: keys.analyze(question),
    queryFn: () => api.analyze(question),
    enabled: question.trim() !== '',
    staleTime: Infinity,
    gcTime: 30 * 60_000,
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  })

export function useSyncNow() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: api.syncNow,
    onSuccess: () =>
      Promise.all([qc.invalidateQueries({ queryKey: keys.folder }), qc.invalidateQueries({ queryKey: ['files'] })]),
  })
}

export function useLogout() {
  const qc = useQueryClient()
  return useMutation({ mutationFn: api.logout, onSuccess: () => qc.clear() })
}
