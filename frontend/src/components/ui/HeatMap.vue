<template>
  <div class="overflow-x-auto">
    <table class="w-full text-xs border-separate" style="border-spacing: 3px">
      <thead>
        <tr>
          <th class="text-left p-1 font-display text-2xs uppercase tracking-label text-ctrl-muted"></th>
          <th v-for="s in steps" :key="s" class="p-1 font-display text-2xs text-ctrl-muted text-center">{{ s }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="row.area">
          <td class="p-1 text-ctrl-text truncate max-w-[11rem]" :title="row.area">{{ row.area }}</td>
          <td v-for="(v, i) in row.steps" :key="i">
            <div class="rounded h-7 flex items-center justify-center tabnum text-2xs font-medium" :style="cellStyle(v)">{{ v }}</div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  steps: { type: Array, default: () => [] },
  rows:  { type: Array, default: () => [] },   // [{ area, steps: [n,n,...] }]
})

const max = computed(() => Math.max(1, ...props.rows.flatMap((r) => r.steps || [])))

function cellStyle(v) {
  const t = (v || 0) / max.value
  const l = 16 + t * 42          // 16% → 58% lightness
  const c = 0.02 + t * 0.13      // chroma scales with intensity
  return { background: `oklch(${l}% ${c} 250)`, color: t > 0.45 ? '#fff' : 'oklch(70% 0.02 250)' }
}
</script>
