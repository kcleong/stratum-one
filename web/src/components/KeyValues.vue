<script setup lang="ts">
defineProps<{ items: [string, string][] }>()
</script>

<template>
  <dl>
    <template v-for="[k, v] in items" :key="k">
      <dt>{{ k }}</dt>
      <dd class="num">{{ v }}</dd>
    </template>
  </dl>
</template>

<style scoped>
dl {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 4px 16px;
  margin: 0;
  font-size: 13px;
}
dt {
  color: var(--ink-2);
}
dd {
  margin: 0;
  text-align: right;
  overflow-wrap: anywhere;
}
</style>
