<script lang="ts">
import { ref } from 'vue'
// Only one tip is open at a time across the page.
const openId = ref<string | null>(null)
let seq = 0
</script>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref as vref, watch } from 'vue'

// Explanation behind an ⓘ: hover or focus on desktop, tap on touch. Teleported so
// table scrollers and cards don't clip it.
const props = defineProps<{ text: string; label: string }>()

const id = `info-${++seq}`
const open = computed(() => openId.value === id)
const button = vref<HTMLButtonElement | null>(null)
const tip = vref<HTMLElement | null>(null)
const pos = vref({ left: 0, top: 0 })

const GUTTER = 16
const GAP = 6

function show() {
  openId.value = id
}
function hide() {
  if (open.value) openId.value = null
}
// A tap focuses (opens) before the click lands, so decide from the state before the tap:
// a second tap closes, while a mouse click or Enter keeps it open.
let closeOnClick = false
function onPointerdown(e: PointerEvent) {
  closeOnClick = open.value && e.pointerType !== 'mouse'
}
function onClick() {
  closeOnClick ? hide() : show()
  closeOnClick = false
}

async function place() {
  await nextTick()
  const b = button.value?.getBoundingClientRect()
  const t = tip.value
  if (!b || !t) return
  const w = t.offsetWidth
  const h = t.offsetHeight
  const left = Math.min(Math.max(b.left + b.width / 2 - w / 2, GUTTER), window.innerWidth - GUTTER - w)
  const below = b.bottom + GAP
  const top = below + h > window.innerHeight - GUTTER && b.top - GAP - h >= GUTTER ? b.top - GAP - h : below
  pos.value = { left, top }
}

function onOutside(e: PointerEvent) {
  const target = e.target as Node
  if (!button.value?.contains(target) && !tip.value?.contains(target)) hide()
}
function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') hide()
}

function listen(on: boolean) {
  const method = on ? 'addEventListener' : 'removeEventListener'
  document[method]('pointerdown', onOutside as EventListener, true)
  document[method]('keydown', onKey as EventListener)
  window[method]('scroll', hide, true)
  window[method]('resize', hide)
}

watch(open, (o) => {
  listen(o)
  if (o) place()
})
onBeforeUnmount(() => {
  hide()
  listen(false)
})
</script>

<template>
  <button
    ref="button"
    type="button"
    class="info"
    :aria-label="`About ${props.label}`"
    :aria-expanded="open"
    :aria-describedby="open ? id : undefined"
    @pointerenter="(e) => e.pointerType === 'mouse' && show()"
    @pointerleave="(e) => e.pointerType === 'mouse' && hide()"
    @focus="show"
    @blur="hide"
    @pointerdown="onPointerdown"
    @click="onClick"
  >
    ⓘ
  </button>
  <Teleport to="body">
    <span v-if="open" :id="id" ref="tip" role="tooltip" class="info-tip" :style="{ left: `${pos.left}px`, top: `${pos.top}px` }">
      {{ props.text }}
    </span>
  </Teleport>
</template>

<style scoped>
.info {
  display: inline-grid;
  place-items: center;
  width: 16px;
  height: 16px;
  padding: 0;
  margin: 0;
  border: 0;
  background: none;
  font: inherit;
  font-size: 13px;
  line-height: 1;
  color: var(--muted);
  cursor: help;
  vertical-align: middle;
}
.info:hover,
.info[aria-expanded='true'] {
  color: var(--ink-2);
}
.info:focus-visible {
  outline: 2px solid var(--series-1);
  outline-offset: 1px;
  border-radius: 50%;
}
.info-tip {
  position: fixed;
  z-index: 100;
  max-width: min(280px, calc(100vw - 32px));
  padding: 8px 10px;
  border: 1px solid var(--grid);
  border-radius: 8px;
  background: var(--surface);
  color: var(--ink);
  font-family: var(--sans);
  font-size: 12px;
  font-weight: 400;
  line-height: 1.45;
  text-align: left;
  white-space: normal;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  pointer-events: none;
}
</style>
