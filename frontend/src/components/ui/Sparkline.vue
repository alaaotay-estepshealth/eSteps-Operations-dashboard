<template>
  <svg :width="width" :height="height" class="inline-block align-middle" :class="$attrs.class">
    <polyline
      :points="points"
      fill="none"
      :stroke="color"
      stroke-width="1.5"
      stroke-linecap="round"
      stroke-linejoin="round"
    />
    <circle
      v-if="data.length"
      :cx="lastX"
      :cy="lastY"
      r="2"
      :fill="color"
    />
  </svg>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  data:   { type: Array, required: true },
  width:  { type: Number, default: 64 },
  height: { type: Number, default: 20 },
  color:  { type: String, default: 'oklch(75% 0.12 205)' },
})

const points = computed(() => {
  if (!props.data.length) return ''
  const max = Math.max(...props.data, 1)
  const pad = 2
  const w = props.width - pad * 2
  const h = props.height - pad * 2
  return props.data
    .map((v, i) => {
      const x = pad + (i / Math.max(props.data.length - 1, 1)) * w
      const y = pad + h - (v / max) * h
      return `${x},${y}`
    })
    .join(' ')
})

const lastX = computed(() => {
  if (!props.data.length) return 0
  const pad = 2
  const w = props.width - pad * 2
  return pad + ((props.data.length - 1) / Math.max(props.data.length - 1, 1)) * w
})

const lastY = computed(() => {
  if (!props.data.length) return 0
  const max = Math.max(...props.data, 1)
  const pad = 2
  const h = props.height - pad * 2
  const last = props.data[props.data.length - 1]
  return pad + h - (last / max) * h
})
</script>
