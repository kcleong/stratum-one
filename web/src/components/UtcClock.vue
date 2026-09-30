<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

const props = defineProps<{ clockDelta: number; leapseconds: number | null | undefined; reference: string | null }>()

const now = ref(Date.now())
let timer: number | undefined
onMounted(() => (timer = window.setInterval(() => (now.value = Date.now()), 100)))
onBeforeUnmount(() => clearInterval(timer))

// lobsang's clock, not the browser's: shift by the delta measured from each status push.
const server = computed(() => new Date(now.value + props.clockDelta * 1000))
const pad = (n: number) => String(n).padStart(2, '0')
const hms = computed(() => {
  const d = server.value
  return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`
})
const date = computed(() =>
  server.value.toLocaleDateString(undefined, { weekday: 'short', year: 'numeric', month: 'short', day: 'numeric', timeZone: 'UTC' }),
)
const local = computed(() => server.value.toLocaleTimeString(undefined, { hour12: false, timeZoneName: 'short' }))
const browserOff = computed(() => {
  const ms = -props.clockDelta * 1000
  return `${ms >= 0 ? '+' : '−'}${Math.abs(ms).toFixed(0)} ms`
})
</script>

<template>
  <div class="clock card">
    <div class="label">UTC</div>
    <div class="hms num">{{ hms }}</div>
    <div class="date">{{ date }}</div>
    <div class="sub">
      Local {{ local }} · GPS−UTC {{ leapseconds ?? '–' }} s · ref {{ reference ?? '–' }} · this browser
      <span class="num">{{ browserOff }}</span>
    </div>
  </div>
</template>

<style scoped>
.clock {
  display: flex;
  flex-direction: column;
  justify-content: center;
}
.label {
  font-size: 12px;
  color: var(--ink-2);
}
.hms {
  font-size: clamp(40px, 7vw, 64px);
  font-weight: 600;
  line-height: 1.05;
  letter-spacing: -0.02em;
}
.date {
  font-size: 15px;
  color: var(--ink-2);
  margin: 2px 0 6px;
}
</style>
