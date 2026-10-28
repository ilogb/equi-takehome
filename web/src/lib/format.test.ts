import { describe, expect, it } from 'vitest'
import { formatMoney, formatPercent } from './format'

describe('formatPercent', () => {
  it('turns a fraction string into a percentage with two decimals', () => {
    expect(formatPercent('0.0842')).toBe('8.42%')
    expect(formatPercent('0.0123')).toBe('1.23%')
    expect(formatPercent('1')).toBe('100.00%')
    expect(formatPercent('0')).toBe('0.00%')
  })
  it('uses U+2212 for negatives', () => {
    expect(formatPercent('-0.005')).toBe('−0.50%')
    expect(formatPercent('-0.005')).not.toContain('-')
  })
  it('rounds half away from zero without float error', () => {
    expect(formatPercent('0.08425')).toBe('8.43%')
    expect(formatPercent('-0.08425')).toBe('−8.43%')
    expect(formatPercent('0.00005')).toBe('0.01%')
  })
  it('never shows a negative zero', () => {
    expect(formatPercent('-0.000001')).toBe('0.00%')
  })
  it('keeps precision of long NUMERIC(24,10) strings', () => {
    expect(formatPercent('0.0842000000')).toBe('8.42%')
  })
  it('returns an em dash for missing values', () => {
    expect(formatPercent(null)).toBe('—')
  })
})

describe('formatMoney', () => {
  it('formats USD with grouping and cents', () => {
    expect(formatMoney('24963108.45', 'USD')).toBe('$24,963,108.45')
  })
  it('keeps exact digits beyond float precision', () => {
    expect(formatMoney('12345678901234567.89', 'USD')).toBe('$12,345,678,901,234,567.89')
  })
  it('uses U+2212 for negatives', () => {
    expect(formatMoney('-1500', 'USD')).toBe('−$1,500.00')
  })
  it('drops the sign when the value rounds to zero', () => {
    expect(formatMoney('-0.001', 'USD')).toBe('$0.00')
    expect(formatMoney('-0.004', null)).toBe('0.00')
  })
  it('falls back to plain grouping without a currency', () => {
    expect(formatMoney('1234.5', null)).toBe('1,234.50')
  })
})
