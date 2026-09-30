/** Seconds to a readable offset: ns, µs, ms or s, signed. */
export function fmtOffset(s: number | null | undefined, digits = 2): string {
  if (s == null) return '–'
  const a = Math.abs(s)
  const sign = s < 0 ? '−' : s > 0 ? '+' : ''
  if (a < 1e-6) return `${sign}${(a * 1e9).toFixed(0)} ns`
  if (a < 1e-3) return `${sign}${(a * 1e6).toFixed(digits)} µs`
  if (a < 1) return `${sign}${(a * 1e3).toFixed(digits)} ms`
  return `${sign}${a.toFixed(digits)} s`
}

/** Unsigned magnitude (RMS, error bars). */
export function fmtSpan(s: number | null | undefined, digits = 2): string {
  return s == null ? '–' : fmtOffset(Math.abs(s), digits).replace('+', '')
}

export function fmtNum(v: number | null | undefined, digits = 0, unit = ''): string {
  if (v == null) return '–'
  return v.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits }) + unit
}

export function fmtAgo(s: number | null | undefined): string {
  if (s == null) return '–'
  if (s < 60) return `${Math.round(s)} s`
  if (s < 3600) return `${Math.round(s / 60)} min`
  if (s < 86400) return `${(s / 3600).toFixed(1)} h`
  return `${(s / 86400).toFixed(1)} d`
}

export function fmtUptime(s: number | null | undefined): string {
  if (s == null) return '–'
  const d = Math.floor(s / 86400)
  const h = Math.floor((s % 86400) / 3600)
  const m = Math.floor((s % 3600) / 60)
  return d ? `${d}d ${h}h ${m}m` : `${h}h ${m}m`
}

export function fmtBytes(b: number | null | undefined): string {
  if (b == null) return '–'
  const units = ['B', 'KB', 'MB', 'GB']
  let i = 0
  while (b >= 1024 && i < units.length - 1) {
    b /= 1024
    i++
  }
  return `${b.toFixed(i ? 1 : 0)} ${units[i]}`
}

/** chrony poll/interval exponents are log2 seconds. */
export function fmtLog2(n: number | null | undefined): string {
  if (n == null) return '–'
  const s = 2 ** n
  return s < 1 ? `${s.toFixed(3)} s` : fmtAgo(s)
}
