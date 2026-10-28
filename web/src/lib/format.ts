/** Number formatting for backend decimal strings. Never goes through float. */

const MINUS = '−'
const DASH = '—'

interface Parsed {
  negative: boolean
  /** All digits, no separator. */
  digits: string
  /** Count of digits after the decimal point. */
  scale: number
}

function parseDecimal(value: string): Parsed | null {
  const m = /^([+-])?(\d*)(?:\.(\d*))?$/.exec(value.trim())
  if (!m || (!m[2] && !m[3])) return null
  const frac = m[3] ?? ''
  return { negative: m[1] === '-', digits: (m[2] || '0') + frac, scale: frac.length }
}

/** Round |value| * 10^places to an integer, half away from zero, as BigInt. */
function scaledRounded(p: Parsed, places: number): bigint {
  const n = BigInt(p.digits)
  const shift = places - p.scale
  if (shift >= 0) return n * 10n ** BigInt(shift)
  const div = 10n ** BigInt(-shift)
  const q = n / div
  return n % div * 2n >= div ? q + 1n : q
}

/** "0.0842" -> "8.42%"; negatives use U+2212; null -> em dash. */
export function formatPercent(value: string | null | undefined): string {
  if (value == null) return DASH
  const p = parseDecimal(value)
  if (!p) return DASH
  // fraction -> percent is x100, so 2 percent decimals = 4 fraction decimals
  const hundredths = scaledRounded(p, 4)
  const s = hundredths.toString().padStart(3, '0')
  const text = `${s.slice(0, -2)}.${s.slice(-2)}%`
  return p.negative && hundredths !== 0n ? MINUS + text : text
}

/** "24963108.45","USD" -> "$24,963,108.45". Exact for any digit count. */
export function formatMoney(value: string | null | undefined, currency: string | null | undefined): string {
  if (value == null || !parseDecimal(value)) return DASH
  const abs = value.trim().replace(/^[+-]/, '')
  const options: Intl.NumberFormatOptions = currency
    ? { style: 'currency', currency }
    : { minimumFractionDigits: 2, maximumFractionDigits: 2 }
  let text: string
  try {
    // Intl accepts decimal strings and keeps their exact digits.
    text = new Intl.NumberFormat('en-US', options).format(abs as unknown as number)
  } catch {
    // An unknown currency code (e.g. "US$" or "points") throws a RangeError: show the
    // plain number followed by the currency text as written.
    const plain = new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    text = `${plain.format(abs as unknown as number)} ${currency}`
  }
  // The sign comes from the rounded output, so "-0.001" shows as $0.00, not -$0.00.
  return value.trim().startsWith('-') && /[1-9]/.test(text) ? MINUS + text : text
}

/** "4500000000","EUR" -> "€4.5B". For headline display only: rounds through a float, unlike formatMoney. */
export function formatMoneyCompact(value: string | null | undefined, currency: string | null | undefined): string {
  if (value == null || !parseDecimal(value)) return DASH
  const n = Number(value)
  const compact = { notation: 'compact', maximumFractionDigits: 2 } as const
  try {
    if (currency) return new Intl.NumberFormat('en-US', { ...compact, style: 'currency', currency }).format(n)
  } catch {
    return `${new Intl.NumberFormat('en-US', compact).format(n)} ${currency}`
  }
  return new Intl.NumberFormat('en-US', compact).format(n)
}
