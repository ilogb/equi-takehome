import { describe, expect, it } from 'vitest'
import { documentIdFromParam, documentPath } from './paths'

describe('documentPath', () => {
  it('puts the id first, then the file name without its extension in lowercase-dash form', () => {
    expect(documentPath(6, 'blackrock-ishares_factsheet_swda_2026-09.pdf')).toBe(
      '/documents/6-blackrock-ishares-factsheet-swda-2026-09',
    )
  })
  it('drops accents and punctuation and collapses runs of separators', () => {
    expect(documentPath(9, 'Q3 Letter — Société Générale (FWD).eml')).toBe('/documents/9-q3-letter-societe-generale-fwd')
  })
  it('caps very long names and falls back to the id alone when nothing is left', () => {
    expect(documentPath(1, `${'a'.repeat(200)}.pdf`)).toBe(`/documents/1-${'a'.repeat(80)}`)
    expect(documentPath(3, '….pdf')).toBe('/documents/3')
    expect(documentPath(4, null)).toBe('/documents/4')
  })
})

describe('documentIdFromParam', () => {
  it('reads the leading id from old and new links', () => {
    expect(documentIdFromParam('6')).toBe(6)
    expect(documentIdFromParam('6-blackrock-ishares-factsheet')).toBe(6)
    expect(documentIdFromParam('2026-letter')).toBe(2026)
  })
  it('rejects links without a leading id', () => {
    expect(documentIdFromParam('blackrock')).toBeNaN()
    expect(documentIdFromParam(undefined)).toBeNaN()
  })
})
