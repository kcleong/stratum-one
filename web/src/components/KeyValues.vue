<script setup lang="ts">
import { INFO } from '../lib/glossary'
import InfoTip from './InfoTip.vue'

defineProps<{ items: [string, string][] }>()
</script>

<template>
  <dl>
    <template v-for="[k, v] in items" :key="k">
      <dt>{{ k }} <InfoTip v-if="INFO[k]" :text="INFO[k]" :label="k" /></dt>
      <dd class="num">{{ v }}</dd>
    </template>
  </dl>
</template>

<style scoped>
/* No gaps, padding instead, so alternate rows form one continuous stripe (see tables). */
dl {
  display: grid;
  grid-template-columns: auto 1fr;
  margin: 0;
  font-size: 13px;
}
dt,
dd {
  padding: 2px 8px;
}
dt {
  color: var(--ink-2);
}
dd {
  margin: 0;
  text-align: right;
  overflow-wrap: anywhere;
}
dt:nth-of-type(even),
dd:nth-of-type(even) {
  background: var(--stripe);
}
</style>
