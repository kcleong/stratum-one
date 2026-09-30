<script setup lang="ts">
import { computed } from 'vue'
import type { GpsStatus } from '../api/types'
import { CONSTELLATIONS } from '../lib/gnss'

const props = defineProps<{ gps: GpsStatus }>()
const rows = computed(() =>
  CONSTELLATIONS.filter((c) => props.gps.constellations[c.name]).map((c) => ({ ...c, ...props.gps.constellations[c.name] })),
)
</script>

<template>
  <ul class="legend">
    <li v-for="c in rows" :key="c.name">
      <span class="glyph" :style="{ color: `var(--series-${c.slot})` }" aria-hidden="true">{{ c.glyph }}</span>
      {{ c.name }} <span class="num sub">{{ c.used }}/{{ c.visible }}</span>
    </li>
    <li class="sub">filled = used · hollow/faded = not used</li>
  </ul>
</template>

<style scoped>
.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 14px;
  list-style: none;
  margin: 0;
  padding: 0;
  font-size: 12px;
}
.glyph {
  margin-right: 2px;
}
</style>
