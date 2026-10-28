/** Readable, bookmarkable document links: /documents/6-blackrock-ishares-factsheet-swda-2026-09.
 *  The leading id is what the page reads, so a renamed file's old links keep working. */

const MAX_SLUG = 80

function slug(name: string | null | undefined): string {
  return (name ?? '')
    .replace(/\.[a-z0-9]{1,5}$/i, '') // file extension
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '') // accents
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .slice(0, MAX_SLUG)
    .replace(/^-+|-+$/g, '')
}

export function documentPath(id: number, name: string | null | undefined): string {
  const s = slug(name)
  return s ? `/documents/${id}-${s}` : `/documents/${id}`
}

export function documentIdFromParam(param: string | undefined): number {
  const m = /^(\d+)(?:-|$)/.exec(param ?? '')
  return m ? Number(m[1]) : NaN
}
