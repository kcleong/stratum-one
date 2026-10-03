/** Patches with sightings but mostly no signal: the antenna can't see that part of the sky. */
export const BLOCKED_BELOW = 0.5 // received / sightings
export const SNR_WEAK = 15
export const SNR_STRONG = 45

/** Average SNR to colour: red (weak) through yellow to green (strong); grey when blocked. */
export function coverageColor(cell: { samples: number; received: number; mean_snr: number | null }): string {
  if (!cell.samples || cell.received / cell.samples < BLOCKED_BELOW || cell.mean_snr == null) return 'hsl(220 8% 55% / 0.45)'
  const f = Math.min(1, Math.max(0, (cell.mean_snr - SNR_WEAK) / (SNR_STRONG - SNR_WEAK)))
  return `hsl(${Math.round(f * 130)} 70% 48% / 0.75)`
}
