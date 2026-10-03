// Regional-indicator pair: "NL" -> 🇳🇱
export const flag = (cc: string) => String.fromCodePoint(...[...cc.toUpperCase()].map((ch) => 0x1f1a5 + ch.charCodeAt(0)))

const regionName = new Intl.DisplayNames(undefined, { type: 'region' })

/** Country name in the browser's language, for tooltips; the code itself if unknown. */
export const countryName = (cc: string) => {
  try {
    return regionName.of(cc) ?? cc
  } catch {
    return cc
  }
}
