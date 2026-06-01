<template>
  <div class="flex items-center gap-5">
    <svg viewBox="0 0 42 42" class="flex-shrink-0" :style="{ width: size + 'px', height: size + 'px' }">
      <circle cx="21" cy="21" r="15.915" fill="none" stroke="var(--ctrl-border, #2a2a2a)" stroke-width="4" />
      <circle
        v-for="(seg, i) in segments"
        :key="i"
        cx="21" cy="21" r="15.915" fill="none"
        :stroke="seg.color"
        stroke-width="4"
        :stroke-dasharray="`${seg.pct} ${100 - seg.pct}`"
        :stroke-dashoffset="seg.offset"
        :class="clickable ? 'cursor-pointer transition-all hover:opacity-80' : ''"
        @click="clickable && $emit('select', seg.item, i)"
      />
      <text x="21" y="20" text-anchor="middle" class="fill-ctrl-text" style="font-size:7px;font-weight:600">{{ total }}</text>
      <text x="21" y="26" text-anchor="middle" class="fill-ctrl-dim" style="font-size:3px;text-transform:uppercase">{{ centerLabel }}</text>
    </svg>
    <div class="flex-1 min-w-0 space-y-1">
      <div v-for="(seg, i) in segments" :key="i" class="flex items-center gap-2 text-xs">
        <span class="w-2 h-2 rounded-sm flex-shrink-0" :style="{ background: seg.color }" />
        <span class="text-ctrl-muted truncate flex-1">{{ seg.label }}</span>
        <span class="tabnum text-ctrl-dim">{{ seg.value }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  data:        { type: Array,  required: true },        // [{ label, value, color }]
  size:        { type: Number, default: 120 },
  centerLabel: { type: String, default: 'total' },
  clickable:   { type: Boolean, default: false },
})

defineEmits(['select'])

const total = computed(() => props.data.reduce((s, d) => s + (d.value || 0), 0))

const segments = computed(() => {
  let cumulative = 0
  const t = total.value || 1
  return props.data.map((d) => {
    const pct = Math.round(((d.value || 0) / t) * 100)
    const offset = 25 - cumulative   // start at top (12 o'clock)
    cumulative += pct
    return { label: d.label, value: d.value, color: d.color, pct, offset: (offset + 100) % 100, item: d }
  })
})
</script>
