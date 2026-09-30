<script setup lang="ts">
// Status is shown with an icon + label, never colour alone.
defineProps<{ level: 'good' | 'warning' | 'serious' | 'critical' | 'neutral'; label: string; title?: string }>()
const icons = { good: '✓', warning: '!', serious: '!', critical: '✕', neutral: '•' }
</script>

<template>
  <span class="pill" :class="level" :title="title">
    <span class="icon" aria-hidden="true">{{ icons[level] }}</span>{{ label }}
  </span>
</template>

<style scoped>
.pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px 3px 4px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--surface);
  font-size: 12px;
  font-weight: 500;
  color: var(--ink);
  white-space: nowrap;
}
.icon {
  display: inline-grid;
  place-items: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  font-size: 11px;
  font-weight: 700;
  color: #fff;
  background: var(--muted);
}
.good .icon { background: var(--good); }
.warning .icon { background: var(--warning); color: #0b0b0b; }
.serious .icon { background: var(--serious); color: #0b0b0b; }
.critical .icon { background: var(--critical); }
</style>
