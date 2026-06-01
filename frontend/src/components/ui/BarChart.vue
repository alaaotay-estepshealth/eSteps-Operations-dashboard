<template>
  <div class="w-full">
    <div class="flex items-end gap-2" :style="{ height: height + 'px' }">
      <div
        v-for="(d, i) in data"
        :key="i"
        class="flex-1 flex flex-col items-center justify-end gap-1.5 group"
        :class="clickable ? 'cursor-pointer' : ''"
        @click="clickable && $emit('select', d, i)"
      >
        <span class="text-2xs tabnum text-ctrl-muted group-hover:text-ctrl-text transition-colors">{{ d.value }}</span>
        <div
          class="w-full rounded-t transition-all duration-300"
          :class="clickable ? 'group-hover:brightness-125' : ''"
          :style="{ height: barHeight(d.value) + '%', minHeight: '2px', background: d.color || 'oklch(62% 0.12 250)' }"
        />
      </div>
    </div>
    <div class="flex gap-2 mt-1.5">
      <div v-for="(d, i) in data" :key="i" class="flex-1 text-center text-2xs text-ctrl-dim truncate" :title="d.label">
        {{ d.label }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  data:      { type: Array,  required: true },   // [{ label, value, color? }]
  height:    { type: Number, default: 140 },
  clickable: { type: Boolean, default: false },
})

defineEmits(['select'])

const max = computed(() => Math.max(1, ...props.data.map((d) => d.value || 0)))

function barHeight(value) {
  return Math.round(((value || 0) / max.value) * 100)
}
</script>
