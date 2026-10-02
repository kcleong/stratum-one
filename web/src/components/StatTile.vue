<script setup lang="ts">
import InfoTip from './InfoTip.vue'

defineProps<{ label: string; value: string; sub?: string; info?: string }>()
</script>

<template>
  <div class="tile card">
    <div class="label">{{ label }}<InfoTip v-if="info" :text="info" :label="label" /></div>
    <div class="value num">{{ value }}</div>
    <div v-if="sub" class="sub">{{ sub }}</div>
  </div>
</template>

<style scoped>
.tile {
  padding: 12px 14px;
}
.label {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--ink-2);
}
.value {
  font-size: 22px;
  font-weight: 600;
  margin: 2px 0;
  letter-spacing: -0.01em;
}
</style>
