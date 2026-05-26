<!--
  StatRow — horizontal strip of KPI stats separated by hairline dividers.
  Usage:
    <StatRow :stats="[
      { label: 'Hours Saved', value: '124h', status: 'ok' },
      { label: 'Leads',       value: 47 },
    ]" />
  status: 'ok' | 'info' | 'warn' | 'err' | undefined (neutral)
-->
<template>
  <div class="flex divide-x divide-ctrl-border bg-ctrl-panel rounded-md overflow-hidden relative">
    <div v-if="revalidating" class="absolute top-0 left-0 right-0 h-0.5 bg-status-info/40 overflow-hidden">
      <div class="h-full w-1/3 bg-status-info rounded-full animate-slide" />
    </div>
    <div
      v-for="stat in stats"
      :key="stat.label"
      class="flex-1 min-w-0 px-5 py-4"
    >
      <div class="text-2xs font-display font-medium uppercase tracking-label text-ctrl-muted mb-1.5 truncate">
        {{ stat.label }}
      </div>
      <div
        class="tabnum text-xl font-semibold leading-none truncate"
        :class="valueColor(stat.status)"
      >
        {{ stat.loading ? '—' : stat.value }}
      </div>
      <div v-if="stat.delta != null" class="text-2xs mt-1 truncate tabnum" :class="stat.delta > 0 ? 'text-status-ok' : stat.delta < 0 ? 'text-status-err' : 'text-ctrl-dim'">
        <span v-if="stat.delta > 0">&#9650; +{{ stat.delta }}</span>
        <span v-else-if="stat.delta < 0">&#9660; {{ stat.delta }}</span>
        <span v-else>&#8212; 0</span>
      </div>
      <div v-else-if="stat.sub" class="text-2xs text-ctrl-dim mt-1 truncate">{{ stat.sub }}</div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  stats: { type: Array, required: true },
  revalidating: { type: Boolean, default: false },
})

function valueColor(status) {
  const map = {
    ok:   'text-status-ok',
    info: 'text-status-info',
    warn: 'text-status-warn',
    err:  'text-status-err',
  }
  return map[status] ?? 'text-ctrl-text'
}
</script>
