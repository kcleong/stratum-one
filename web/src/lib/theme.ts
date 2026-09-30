import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

export type ThemePref = 'auto' | 'light' | 'dark'

const pref = ref<ThemePref>(load())
const systemDark = ref(matchMedia('(prefers-color-scheme: dark)').matches)
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => (systemDark.value = e.matches))

function load(): ThemePref {
  try {
    const v = localStorage.getItem('theme')
    if (v === 'light' || v === 'dark') return v
  } catch {
    /* storage blocked: fall back to auto */
  }
  return 'auto'
}

function apply(p: ThemePref) {
  if (p === 'auto') delete document.documentElement.dataset.theme
  else document.documentElement.dataset.theme = p
}
apply(pref.value)

export const isDark = computed(() => (pref.value === 'auto' ? systemDark.value : pref.value === 'dark'))

export function cycleTheme() {
  pref.value = pref.value === 'auto' ? 'light' : pref.value === 'light' ? 'dark' : 'auto'
  apply(pref.value)
  try {
    localStorage.setItem('theme', pref.value)
  } catch {
    /* ignore */
  }
}

export const themePref = pref

/** CSS token values for canvas charts; recomputed when the theme flips. */
export function useTokens() {
  const tick = ref(0)
  const read = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  const tokens = computed(() => {
    void tick.value
    void isDark.value
    return {
      surface: read('--surface'),
      ink: read('--ink'),
      ink2: read('--ink-2'),
      muted: read('--muted'),
      grid: read('--grid'),
      axis: read('--axis'),
      series: (n: number) => read(`--series-${n}`),
    }
  })
  // matchMedia fires before styles recompute in some browsers; re-read on next frame.
  let raf = 0
  onMounted(() => (raf = requestAnimationFrame(() => tick.value++)))
  onBeforeUnmount(() => cancelAnimationFrame(raf))
  return tokens
}
