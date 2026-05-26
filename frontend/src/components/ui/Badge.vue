<template>
  <span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium tabnum" :class="cls">
    <span class="status-dot" :class="dotCls" />
    <slot />
  </span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  variant: { type: String, default: 'default' },
})

const map = {
  success: { cls: 'bg-status-ok-bg text-status-ok',     dot: 'bg-status-ok' },
  warning: { cls: 'bg-status-warn-bg text-status-warn', dot: 'bg-status-warn' },
  error:   { cls: 'bg-status-err-bg text-status-err',   dot: 'bg-status-err' },
  info:    { cls: 'bg-status-info-bg text-status-info', dot: 'bg-status-info' },
  pending: { cls: 'bg-status-warn-bg text-status-warn', dot: 'bg-status-warn' },
  default: { cls: 'bg-ctrl-raised text-ctrl-muted',     dot: 'bg-ctrl-dim' },
}

const entry   = computed(() => map[props.variant] ?? map.default)
const cls     = computed(() => entry.value.cls)
const dotCls  = computed(() => entry.value.dot)
</script>
