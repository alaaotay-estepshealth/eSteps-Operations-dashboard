<template>
  <div class="w-full">
    <svg :viewBox="`0 0 100 ${vh}`" preserveAspectRatio="none" class="w-full" :style="{ height: height + 'px' }">
      <polyline v-if="areaPoints" :points="areaPoints" :fill="color" opacity="0.12" stroke="none" />
      <line
        v-if="target != null"
        x1="0" :y1="targetY" x2="100" :y2="targetY"
        stroke="oklch(70% 0.15 75)" stroke-width="1" stroke-dasharray="3 3"
        vector-effect="non-scaling-stroke"
      />
      <polyline
        :points="linePoints"
        fill="none"
        :stroke="color"
        stroke-width="2"
        vector-effect="non-scaling-stroke"
        stroke-linejoin="round"
        stroke-linecap="round"
      />
    </svg>
    <div class="flex justify-between mt-1.5">
      <span v-for="(d, i) in data" :key="i" class="text-2xs text-ctrl-dim tabnum">{{ d.label }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  data:   { type: Array,  required: true },          // [{ label, value }]
  height: { type: Number, default: 120 },
  color:  { type: String, default: 'oklch(70% 0.15 150)' },
  target: { type: Number, default: null },           // optional target line
})

const vh = 100
const PAD = 8

const max = computed(() => Math.max(1, props.target || 0, ...props.data.map((d) => d.value || 0)))
const min = computed(() => Math.min(0, ...props.data.map((d) => d.value || 0)))

const targetY = computed(() => {
  if (props.target == null) return 0
  const span = max.value - min.value || 1
  return +(vh - PAD - ((props.target - min.value) / span) * (vh - 2 * PAD)).toFixed(2)
})

const pts = computed(() => {
  const n = props.data.length
  const span = max.value - min.value || 1
  return props.data.map((d, i) => {
    const x = n > 1 ? (i / (n - 1)) * 100 : 50
    const y = vh - PAD - (((d.value || 0) - min.value) / span) * (vh - 2 * PAD)
    return { x: +x.toFixed(2), y: +y.toFixed(2) }
  })
})

const linePoints = computed(() => pts.value.map((p) => `${p.x},${p.y}`).join(' '))

const areaPoints = computed(() => {
  if (!pts.value.length) return ''
  const first = pts.value[0], last = pts.value[pts.value.length - 1]
  return `${first.x},${vh} ${linePoints.value} ${last.x},${vh}`
})
</script>
