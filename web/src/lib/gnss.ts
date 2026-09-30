/** Fixed constellation → colour slot / marker / prefix. Colour follows the entity, never its rank. */
export interface Constellation {
  name: string
  slot: number // --series-N
  symbol: string // ECharts symbol
  glyph: string // for HTML legends, matches symbol
  prefix: string // RINEX-style satellite prefix
}

export const CONSTELLATIONS: Constellation[] = [
  { name: 'GPS', slot: 1, symbol: 'circle', glyph: '●', prefix: 'G' },
  { name: 'Galileo', slot: 2, symbol: 'rect', glyph: '■', prefix: 'E' },
  { name: 'SBAS', slot: 3, symbol: 'triangle', glyph: '▲', prefix: 'S' },
  { name: 'BeiDou', slot: 4, symbol: 'diamond', glyph: '◆', prefix: 'C' },
  { name: 'GLONASS', slot: 5, symbol: 'pin', glyph: '⬟', prefix: 'R' },
  { name: 'QZSS', slot: 6, symbol: 'roundRect', glyph: '▢', prefix: 'J' },
  { name: 'NavIC', slot: 7, symbol: 'arrow', glyph: '➤', prefix: 'I' },
  { name: 'IMES', slot: 8, symbol: 'circle', glyph: '○', prefix: 'M' },
]

const byName = new Map(CONSTELLATIONS.map((c) => [c.name, c]))
const unknown: Constellation = { name: 'unknown', slot: 8, symbol: 'circle', glyph: '○', prefix: '?' }

export function constellation(name: string): Constellation {
  return byName.get(name) ?? unknown
}

export function satLabel(gnss: string, svid: number | null, prn: number | null): string {
  return `${constellation(gnss).prefix}${svid ?? prn ?? '?'}`
}
